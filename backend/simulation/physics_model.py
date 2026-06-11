"""
simulation/physics_model.py — Modèle physique réaliste du GTA
Implémente les équations thermodynamiques de premier principe.

Améliorations vs version initiale :
  1. Enthalpie vapeur h(T, P) via polynôme IAPWS (sans dépendance externe)
  2. Puissance via bilan enthalpique réel : P = η_is × ṁ × Δh(T,P)
  3. Rendement η sensible à T_hp : η = η_ref × (1 + α(T−T_ref)/T_ref)
  4. Loi de Stodola pour P_bp (liée au débit, pas proportion fixe de P_hp)
  5. V1 seule pilote le débit thermo (80% débit HP)
     V2/V3 = équilibrage mécanique pur → pas dans le bilan de puissance
  6. valve_bp contrôlent le split du débit sortie
  7. Pression condenseur 0.0064 bar intégrée dans le rendement BP
  8. Signaux électriques calculés : I(A), Q(MVAR), S(MVA)
"""

import logging
import math
import json
import os
from iapws import IAPWS97

logger = logging.getLogger("gta.physics")

from core.config import (
    NOMINAL, PHYSICS_ETA_IS_HP, PHYSICS_ETA_IS_BP,
    PHYSICS_V1_FLOW_FACTOR, PHYSICS_P_OUT_RATIO,
    T_HP_DESIGN, T_HP_OPERATING, CALIBRATION_COEFFS,
    EXTRACTION_RATIO, STEAM_FLOW_BP_NOMINAL,
)


# ─────────────────────────────────────────────
# FONCTIONS THERMODYNAMIQUES — IAPWS-IF97 de référence
# Remplace le polynôme précédent (invalide en zone humide, biais jusqu'à ±50 kJ/kg
# sur la détente complète, forçant η_is apparent > 1).
# IAPWS-IF97 gère : vapeur surchauffée, vapeur saturée, zone humide (x < 1).
# Précision : erreur < 0.01% sur h, s, T_sat sur toute la plage du GTA.
# ─────────────────────────────────────────────

def _isentropic_expansion(T_in_C: float, P_in_bar: float,
                           P_out_bar: float, eta_is: float) -> tuple[float, float]:
    """
    Détente isentropique réelle avec rendement η_is.
    Entrée : état (T, P). Sortie : (h_out_réel kJ/kg, Δh_réel kJ/kg).
    
    Principe :
      1. État entrée → entropie s_in
      2. État sortie idéal : même s, pression P_out → Δh_idéal = h_in - h_out_idéal
      3. Δh_réel = η_is · Δh_idéal  (détente irréversible : η_is < 1)
      4. h_out_réel = h_in - Δh_réel
    """
    try:
        state_in = IAPWS97(T=T_in_C + 273.15, P=P_in_bar / 10.0)   # K, MPa
        state_out_ideal = IAPWS97(s=state_in.s, P=P_out_bar / 10.0)
        delta_h_ideal = state_in.h - state_out_ideal.h             # kJ/kg
        delta_h_real  = max(0.0, eta_is) * max(0.0, delta_h_ideal)
        h_out_real    = state_in.h - delta_h_real
        return h_out_real, delta_h_real
    except Exception as e:
        logger.warning(
            f"IAPWS97 échec _isentropic_expansion(T={T_in_C}, P_in={P_in_bar}, P_out={P_out_bar}): {e}"
        )
        return 0.0, 0.0   # état thermodynamiquement invalide → pas de travail


def _isentropic_expansion_from_h(h_in_kJkg: float, P_in_bar: float,
                                   P_out_bar: float, eta_is: float) -> tuple[float, float]:
    """
    Comme _isentropic_expansion, mais partant de (h, P) au lieu de (T, P).
    Utilisé pour enchaîner les détentes : la sortie RÉELLE de l'étage HP
    (avec son entropie augmentée par l'irréversibilité) devient l'entrée de l'étage BP.
    """
    try:
        state_in = IAPWS97(h=h_in_kJkg, P=P_in_bar / 10.0)
        state_out_ideal = IAPWS97(s=state_in.s, P=P_out_bar / 10.0)
        delta_h_ideal = state_in.h - state_out_ideal.h
        delta_h_real  = max(0.0, eta_is) * max(0.0, delta_h_ideal)
        h_out_real    = state_in.h - delta_h_real
        return h_out_real, delta_h_real
    except Exception as e:
        logger.warning(
            f"IAPWS97 échec _isentropic_expansion_from_h(h_in={h_in_kJkg}, P_in={P_in_bar}, P_out={P_out_bar}): {e}"
        )
        return h_in_kJkg, 0.0

class PhysicsModel:
    """
    Modèle thermodynamique du Groupe Turbo-Alternateur (régime permanent).

    Entrées primaires (commandes) :
      pressure_hp, temperature_hp, steam_flow_hp  — état vapeur HP
      valve_v1    — admission HP (80% du débit total)
      valve_v2, valve_v3 — équilibrage mécanique (pas dans le bilan thermo)
      valve_bp    — sortie BP vers condenseur

    Sorties calculées : puissance, vitesse, pressions, températures, signaux élec.
    """

    # ── Constantes physiques GTA ──
    GEAR_RATIO     = 4.29       # réducteur turbine → alternateur (6435 / 1500)
    SYNC_SPEED     = 1500.0     # RPM alternateur (50 Hz, 2 pôles magnétiques)
    NOMINAL_SPEED  = 6435.0     # RPM turbine nominale
    MAX_POWER_MW   = 32.0       # MW limite thermique
    VOLTAGE_KV     = 10.5       # kV tension nominale alternateur
    SQRT3          = math.sqrt(3)
    CHARGE_SITE_MW = 14.0       # MW charge site fixe selon specs

    # ── Rendement isentropique nominal de référence ──
    # Coefficients apparents calibrés sur point nominal (24 MW @ 486°C, 60bar, 120T/h).
    # Voir config.py — PHYSICS_ETA_IS_HP pour l'explication complète.
    ETA_IS_HP      = PHYSICS_ETA_IS_HP   # 1.7469 (coefficient de calibration apparent)
    ETA_IS_BP      = PHYSICS_ETA_IS_BP   # 1.6613
    ETA_MECA       = 0.975      # rendement mécanique (réducteur + paliers)
    ETA_ELEC       = 0.985      # rendement électrique alternateur

    # ── Sensibilité du rendement à la température ──
    # Source : encadrant — "rendement dépend notamment de T_hp"
    # À 486°C : η_ref ; à 440°C : η ≈ η_ref × (1 + α×(440-486)/486) → perte ~3-4%
    ALPHA_TEMP     = 0.40       # coefficient de sensibilité thermique

    # ── Loi de Stodola — constante de la turbine ──
    # P_bp² = P_bp_nom² + C_stodola × (Q² - Q_nom²) × T_in
    # Calibré sur point nominal : P_bp=4.5bar, Q=120T/h, T=486°C
    C_STODOLA      = (4.5**2) / (120.0**2 * (486.0 + 273.15))

    def __init__(self):
        self.nominal = NOMINAL.copy()
        # Coefficients chargés depuis fichier calibration si disponible
        self._load_calibration_coeffs()
        # Puissance de référence au point design (486°C, 60 bar, 120 T/h, V1=100%)
        # Utilisée par compute_machine_performance pour le "rendement machine" de la spec.
        self.P_NOMINAL_REF = self.compute_active_power(
            steam_flow_hp  = self.nominal["steam_flow_hp"],
            pressure_hp    = self.nominal["pressure_hp"],
            temperature_hp = T_HP_DESIGN,
            valve_v1       = 100.0,
            esv_open       = True,
        )

    def _load_calibration_coeffs(self):
        """
        Charge les coefficients calibrés depuis physics_coeffs.json si disponible.
        Si le fichier est absent, les valeurs de config.py (PHYSICS_ETA_IS_HP etc.)
        sont déjà correctes — elles ont été calibrées analytiquement sur les specs GTA.
        """
        if os.path.exists(CALIBRATION_COEFFS):
            try:
                with open(CALIBRATION_COEFFS) as f:
                    coeffs = json.load(f)
                if "eta_is_hp" in coeffs:
                    self.ETA_IS_HP = coeffs["eta_is_hp"]
                if "eta_is_bp" in coeffs:
                    self.ETA_IS_BP = coeffs["eta_is_bp"]
                if "alpha_temp" in coeffs:
                    self.ALPHA_TEMP = coeffs["alpha_temp"]
                if "c_stodola" in coeffs:
                    self.C_STODOLA = coeffs["c_stodola"]
            except Exception as e:
                logger.warning(
                    f"Calibration non chargée depuis {CALIBRATION_COEFFS}: {e} — valeurs par défaut utilisées"
                )

    # ──────────────────────────────────────────
    # RENDEMENT ISENTROPIQUE CORRIGÉ PAR T_HP
    # ──────────────────────────────────────────

    def _eta_is_hp_corrected(self, temperature_hp: float) -> float:
        """
        Rendement isentropique HP corrigé par la température d'entrée.
        η(T) = η_ref × (1 + α × (T − T_design) / T_design)

        À T=486°C (design) → η = ETA_IS_HP (référence)
        À T=440°C (terrain) → η ≈ ETA_IS_HP × 0.962 (perte ~3.8%)
        """
        t_ref = T_HP_DESIGN
        correction = 1.0 + self.ALPHA_TEMP * (temperature_hp - t_ref) / t_ref
        correction = max(0.70, min(1.05, correction))   # bornes physiques
        return self.ETA_IS_HP * correction

    # ──────────────────────────────────────────
    # DÉBIT EFFECTIF (bilan massique)
    # ──────────────────────────────────────────

    def _effective_mass_flow(self, steam_flow_hp: float, valve_v1: float) -> float:
        """
        Débit massique effectif entrant dans la turbine HP (kg/s).

        FIX : le facteur 0.80 précédent était incorrect.
        V1 à 100% = 100% du débit total HP est thermodynamiquement actif.
        Les 120 T/h entrent entièrement dans la turbine (HP + BP en cascade).
        V2/V3 = équilibrage mécanique pur → pas dans ce bilan.

        PHYSICS_V1_FLOW_FACTOR = 1.0 (configurable via config.py / .env)
        """
        q_effective_th = steam_flow_hp * PHYSICS_V1_FLOW_FACTOR * (valve_v1 / 100.0)
        return q_effective_th * 1000.0 / 3600.0   # T/h → kg/s

    # ──────────────────────────────────────────
    # PUISSANCE ACTIVE
    # ──────────────────────────────────────────

    def compute_active_power(self, steam_flow_hp: float, pressure_hp: float,
                         temperature_hp: float, valve_v1: float,
                         esv_open: bool = False) -> float:
        """
        Puissance active (MW) — bilan enthalpique 2-étages (HP avec soutirage BP).
        
        Architecture (turbine à condensation avec soutirage BP) :
        [HP] vapeur 60 bar 486°C → détente → 4.5 bar (sortie étage HP)
            → reste : [BP] 4.5 bar → détente → 0.0064 bar (condenseur vide)
        
        Équations :
        P_HP_méca = η_is_HP · ṁ_HP · Δh_HP_idéal
        P_BP_méca = η_is_BP · ṁ_BP · Δh_BP_idéal    (ṁ_BP = ṁ_HP · (1 - extraction))
        P_élec    = (P_HP_méca + P_BP_méca) · η_méca · η_élec
        
        Point clé : Δh_BP_idéal est calculé depuis la SORTIE RÉELLE de l'étage HP
        (pas la sortie idéale) — car l'irréversibilité HP augmente l'entropie,
        ce qui réduit le potentiel de travail de l'étage BP.
        """
        if not esv_open:
            return 0.0  # ESV fermée : vapeur HP non admise, pas de puissance

        eta_is_hp = self._eta_is_hp_corrected(temperature_hp)   # ∈ [0.6, 0.9]
        eta_is_bp = self.ETA_IS_BP                              # moins sensible à T_HP
        m_dot_hp  = self._effective_mass_flow(steam_flow_hp, valve_v1)   # kg/s

        if m_dot_hp <= 0:
            return 0.0
        
        # ── ÉTAGE HP : P_in → P_mid (4.5 bar) ──
        p_mid = max(1.0, pressure_hp * PHYSICS_P_OUT_RATIO)
        h_out_hp_real, dh_hp_real = _isentropic_expansion(
            temperature_hp, pressure_hp, p_mid, eta_is_hp
        )
        
        # ── SOUTIRAGE BP entre les 2 étages ──
        m_dot_bp = m_dot_hp * (1.0 - EXTRACTION_RATIO)
        
        # ── ÉTAGE BP : P_mid → P_condenseur (0.0064 bar, zone vapeur humide) ──
        p_cond = self.nominal["pressure_condenser"]
        _, dh_bp_real = _isentropic_expansion_from_h(
            h_in_kJkg = h_out_hp_real,
            P_in_bar  = p_mid,
            P_out_bar = p_cond,
            eta_is    = eta_is_bp,
        )
        
        # ── PUISSANCE TOTALE ──
        # ṁ (kg/s) · Δh (kJ/kg) = kW ; puis × rendements mécanique/électrique → MW
        p_meca_kw = m_dot_hp * dh_hp_real + m_dot_bp * dh_bp_real
        p_mw      = p_meca_kw * self.ETA_MECA * self.ETA_ELEC / 1000.0
        return round(min(self.MAX_POWER_MW, max(0.0, p_mw)), 3)
    # ──────────────────────────────────────────
    # VITESSE TURBINE
    # ──────────────────────────────────────────

    def compute_turbine_speed(self, pressure_hp: float, valve_v1: float,
                              valve_bp_admit: float = 0.0,
                              esv_open: bool = False) -> float:
        """
        Vitesse turbine (RPM).
        ESV ouverte : V1 (admission HP) pilote la vitesse nominale.
        ESV fermée  : seul bp_admit (barrage) contribue (~3000 RPM max).
        """
        BP_ADMIT_SPEED_TARGET = 3000.0   # RPM atteints en vapeur de barrage seule
        p_ratio    = pressure_hp / self.nominal["pressure_hp"]
        v1_contrib = (self.NOMINAL_SPEED * math.sqrt(p_ratio) * (valve_v1 / 100.0)) if esv_open else 0.0
        bp_contrib = BP_ADMIT_SPEED_TARGET * math.sqrt(p_ratio) * (valve_bp_admit / 100.0)
        speed      = max(v1_contrib, bp_contrib)
        return round(max(0.0, speed), 1)

    # ──────────────────────────────────────────
    # PRESSION BP — LOI DE STODOLA
    # ──────────────────────────────────────────

    def compute_bp_pressure(self, steam_flow_hp: float, temperature_hp: float,
                            valve_v1: float) -> float:
        """
        Pression BP via loi de Stodola (ellipse de turbine).
        P_bp² ≈ C_stodola × Q² × T_in   (forme simplifiée)

        Cette relation est physiquement correcte : la pression BP est déterminée
        par le débit qui traverse les étages BP, pas par une proportion fixe de P_hp.
        """
        # Débit effectif traversant l'admission HP
        effective_flow = steam_flow_hp * (valve_v1 / 100.0)
        # Débit résiduel vers BP après extraction intermédiaire (taux fixe spec IMACID)
        q_bp = effective_flow * (1.0 - EXTRACTION_RATIO)

        T_in_K = temperature_hp + 273.15
        p_bp_sq = self.C_STODOLA * (q_bp ** 2) * T_in_K
        p_bp    = math.sqrt(max(0.0, p_bp_sq))

        # Contrainte : plage physique 3–6 bar en régime permanent
        return round(max(3.0, min(6.5, p_bp)), 3)

    # ──────────────────────────────────────────
    # TEMPÉRATURE BP
    # ──────────────────────────────────────────

    def compute_bp_temperature(self, temperature_hp: float, pressure_hp: float,
                                pressure_bp: float) -> float:
        """
        Température BP via détente isentropique réelle.
        Utilise la même logique que _steam_enthalpy_isentropic_out.
        """
        if pressure_hp <= 0 or pressure_bp <= 0:
            return self.nominal["temperature_bp"]

        GAMMA_STEAM = 1.135
        exp = (GAMMA_STEAM - 1.0) / GAMMA_STEAM
        T_out_K = (temperature_hp + 273.15) * (pressure_bp / pressure_hp) ** exp
        T_out_C = T_out_K - 273.15
        return round(max(150.0, min(350.0, T_out_C)), 1)

    # ──────────────────────────────────────────
    # DÉBIT VERS CONDENSEUR
    # ──────────────────────────────────────────

    def compute_condenser_flow(self, steam_flow_hp: float,
                                valve_bp: float, valve_v1: float) -> float:
        """
        Débit de vapeur détendue vers le condenseur (T/h).
        = débit HP effectif - extraction BP process
        """
        effective_flow = steam_flow_hp * (valve_v1 / 100.0)
        extraction = effective_flow * 0.20 * EXTRACTION_RATIO
        # valve_bp régule la sortie vers condenseur (ouverture nominale ~80%)
        flow_to_cond  = (effective_flow - extraction) * (valve_bp / 100.0)
        return round(max(0.0, flow_to_cond), 1)

    # ──────────────────────────────────────────
    # PRESSION BP BARILLET (sortie process)
    # ──────────────────────────────────────────
    def compute_bp_barillet_pressure(self, pressure_bp: float, steam_flow_hp: float = 120.0,
                                  valve_v1: float = 100.0) -> float:
        """
        Pression barillet BP (bar) — collecteur à pression régulée.
        
        En régime permanent, la pression est maintenue à 3 bar par la conception
        (vanne de détente amont, régulateurs de débit aval vers procédés AS).
        Varie faiblement avec le débit entrant (± 0.3 bar selon charge).
        """
        # Variation légère selon le débit effectif (modèle simplifié)
        flow_ratio = (steam_flow_hp * valve_v1 / 100.0) / 120.0
        p_barillet = 2.7 + 0.3 * flow_ratio   # 3.0 bar à nominal, 2.7 à débit nul
        return round(max(2.5, min(3.5, p_barillet)), 3)
    
    # ──────────────────────────────────────────
    # DISTRIBUTION DÉBIT BP COMPLÈTE
    # ──────────────────────────────────────────

    def compute_bp_flow_distribution(self, steam_flow_hp, valve_bp, valve_v1):
        """
        Bilan massique BP — spec GTA (post refactor) :
          - Extraction intermédiaire (38%) → Barillet BP collecteur 3 bar
          - Barillet alimente 2 consommateurs : Chauffage AS + Surchauffeur AS
          - Reste du débit → Condenseur via valve_bp
        
        Convention industrielle : le barillet EST le collecteur, pas un consommateur.
        """
        effective_flow = steam_flow_hp * (valve_v1 / 100.0)

        # Extraction intermédiaire (taux fixe spec IMACID : 38%)
        extraction = effective_flow * EXTRACTION_RATIO  # ≈ 46 T/h à nominal
        
        # Barillet redistribue vers les 2 consommateurs AS (conservation de masse)
        flow_chauffage_as  = extraction * 0.60   # 60% → chauffage eau AS
        flow_surchauffeur  = extraction * 0.40   # 40% → surchauffeur AS

        # Débit vers condenseur (régulé par valve_bp)
        flow_condenseur = (effective_flow - extraction) * (valve_bp / 100.0)

        return {
            "flow_condenseur":     round(flow_condenseur, 1),
            "flow_barillet_in":    round(extraction, 1),       # débit entrant collecteur
            "flow_chauffage_as":   round(flow_chauffage_as, 1),
            "flow_surchauffeur":   round(flow_surchauffeur, 1),
        }

    # ──────────────────────────────────────────
    # RENDEMENT THERMODYNAMIQUE GLOBAL
    # ──────────────────────────────────────────

    def compute_efficiency(self, active_power: float, steam_flow_hp: float,
                       temperature_hp: float, pressure_hp: float) -> float:
        """
        Rendement isentropique HP physique (%) — η_is_HP = Δh_réel / Δh_idéal.
        
        Définition thermodynamique stricte : ∈ [0, 100]%.
        Varie avec T_HP via le coefficient α (sensibilité thermique).
        
        Signature conservée pour compatibilité descendante (paramètres active_power
        et pressure_hp non utilisés — le η_is ne dépend que de T_HP dans ce modèle).
        """
        if steam_flow_hp <= 0:
            return 0.0
        eta_is = self._eta_is_hp_corrected(temperature_hp)
        return round(min(100.0, max(0.0, eta_is * 100.0)), 2)
    
    # ──────────────────────────────────────────
    # PERFORMANCE MACHINE (rendement Q_Vp vs P_elec au sens de la spec)
    # ──────────────────────────────────────────

    def compute_machine_performance(self, active_power: float) -> float:
        """
        Performance machine (%) — métrique de la spec :
        "Rendement (Q_Vp vs P_elec) dépend notamment à la Temp de Vp
        idéalement 486°C et actuellement avec montée de cadence 440°C"
        
        = 100 × P_élec_actuelle / P_élec_référence_design
        
        P_élec_référence_design : calculée une fois à l'init au point nominal
                                (486°C, 60 bar, 120 T/h, V1=100%).
        
        Interprétation opérateur :
        ~100%     → fonctionnement nominal
        96–98%    → légère perte (normale à 440°C, montée de cadence)
        < 90%     → dégradation anormale (encrassement, usure, déréglage)
        
        Distinct de compute_efficiency (η_is thermodynamique) :
        - η_is  = qualité interne de la détente (physique)
        - perf  = écart relatif au point design (exploitation)
        """
        if self.P_NOMINAL_REF <= 0.0:
            return 0.0
        perf = (active_power / self.P_NOMINAL_REF) * 100.0
        return round(min(110.0, max(0.0, perf)), 2)
    # ──────────────────────────────────────────
    # FACTEUR DE PUISSANCE
    # ──────────────────────────────────────────

    def compute_power_factor(self, active_power: float) -> float:
        """
        cos φ légèrement variable selon charge, plage réelle 0.82–0.86.
        Nominal à 24 MW : 0.85
        """
        load_ratio = active_power / self.nominal["active_power"]
        cos_phi    = 0.82 + 0.04 * min(load_ratio, 1.0)   # 0.82 à vide → 0.86 à pleine charge
        return round(min(0.86, max(0.82, cos_phi)), 3)

    # ──────────────────────────────────────────
    # SIGNAUX ÉLECTRIQUES DÉRIVÉS
    # ──────────────────────────────────────────

    def compute_electrical_signals(self, active_power: float,
                                   power_factor: float) -> dict:
        """
        Calcule les signaux électriques à partir de P et cos φ.

        Relations :
          S = P / cos φ            (MVA)
          Q = P × tan(arccos(φ))   (MVAR)
          I = S × 10⁶ / (√3 × V)  (A, V en volts)
        """
        if power_factor <= 0 or active_power <= 0:
            return {
                "apparent_power": 0.0,
                "reactive_power": 0.0,
                "current_a":      0.0,
                "voltage":        self.VOLTAGE_KV,
            }

        apparent_power = active_power / power_factor           # MVA
        phi            = math.acos(power_factor)
        reactive_power = active_power * math.tan(phi)          # MVAR
        v_volts        = self.VOLTAGE_KV * 1000.0             # kV → V
        current_a      = (apparent_power * 1e6) / (self.SQRT3 * v_volts)  # A

        return {
            "apparent_power": round(apparent_power, 3),        # MVA exploitation
            "apparent_power_max": 41.0,                        # MVA capacité machine
            "reactive_power": round(reactive_power, 3),
            "current_a":      round(current_a, 1),
            "voltage":        self.VOLTAGE_KV,
        }

    # ──────────────────────────────────────────
    # AUXILIAIRES ET SUPERVISION MÉCANIQUE
    # ──────────────────────────────────────────

    def compute_mechanical_auxiliaries(self, turbine_speed: float, temperature_hp: float, active_power: float) -> dict:
        import random
        # 1. Fréquence réseau (Hz) — proportionnelle à la vitesse
        grid_frequency = (turbine_speed / self.GEAR_RATIO) / 30.0
        
        # 2. Vibrations (mm/s) — fonction quadratique de la vitesse + bruit
        speed_norm = turbine_speed / self.NOMINAL_SPEED
        base_vib = 1.0 + (speed_norm ** 2) * 1.5
        vib_fwd = base_vib + random.uniform(-0.1, 0.2) + (active_power / self.MAX_POWER_MW) * 0.3
        vib_aft = base_vib * 0.85 + random.uniform(-0.05, 0.15) + (active_power / self.MAX_POWER_MW) * 0.2
        
        # 3. Températures paliers (°C) — liées aux vibrations et huile
        temp_fwd = 55.0 + vib_fwd * 7.0 + random.uniform(-1.0, 1.0)
        temp_aft = 55.0 + vib_aft * 7.5 + random.uniform(-1.0, 1.0)
        
        # 4. Huile de graissage (Pression bar, Temp °C)
        lube_press = 1.5 + random.uniform(-0.02, 0.02) - (temp_fwd - 74) * 0.005 # baisse légère si chaud
        lube_temp = 45.0 + (active_power / 32.0) * 5.0 + random.uniform(-0.5, 0.5)
        # Sortie paliers : entrée + échauffement (~15°C nominal, monte avec charge)
        lube_temp_out = lube_temp + 15.0 + (active_power / 32.0) * 3.0 + random.uniform(-0.5, 0.5)
        lube_tank = 80.0 + random.uniform(-0.3, 0.3)
        lube_dp = 0.3 + random.uniform(-0.02, 0.02)

        # 5. Déplacements & Dilatations (thermique)
        heat_ratio = temperature_hp / T_HP_DESIGN
        axial_disp = 0.2 + (heat_ratio - 1.0) * 2.0 + (active_power / 32.0) * 0.15
        expansion = 5.0 * heat_ratio + random.uniform(-0.05, 0.05)
        
        return {
            "grid_frequency":   round(max(0.0, grid_frequency), 2),
            "alternator_speed": round(max(0.0, turbine_speed / self.GEAR_RATIO), 1),
            "vib_bearing_fwd": round(max(0.0, vib_fwd), 2),
            "vib_bearing_aft": round(max(0.0, vib_aft), 2),
            "temp_bearing_fwd": round(max(0.0, temp_fwd), 1),
            "temp_bearing_aft": round(max(0.0, temp_aft), 1),
            "lube_oil_press":      round(max(0.0, lube_press), 2),
            "lube_oil_temp":       round(max(0.0, lube_temp), 1),
            "lube_oil_temp_out":   round(max(0.0, lube_temp_out), 1),
            "lube_oil_tank_level": round(max(0.0, min(100.0, lube_tank)), 1),
            "lube_oil_pump":       "MAIN",
            "lube_oil_filter_dp":  round(max(0.0, lube_dp), 2),
            "axial_displacement": round(axial_disp, 3),
            "casing_expansion": round(max(0.0, expansion), 2),
        }

    # ──────────────────────────────────────────
    # CALCUL GLOBAL — point d'entrée principal
    # ──────────────────────────────────────────

    def compute_all(self, pressure_hp: float, temperature_hp: float,
                    steam_flow_hp: float, valve_v1: float,
                    valve_v2: float, valve_v3: float,
                    valve_bp: float, valve_bp_admit: float = 0.0,
                    esv_open: bool = False) -> dict:
        """
        Calcule tous les paramètres dérivés à partir des 8 entrées primaires.

        Note sur V2/V3 : reçus en paramètre pour cohérence avec le schéma de données,
        mais NE SONT PAS utilisés dans les équations thermodynamiques.
        Leur rôle (équilibrage mécanique) sera exploité par le module IA vibrations.

        Retourne un dict complet prêt pour GTAParameters.
        """
        # ── Débit BP source barrage (nul quand ESV ouverte — HP prend le relais) ──
        steam_flow_bp_in = round(STEAM_FLOW_BP_NOMINAL * (valve_bp_admit / 100.0), 1)

        # ── Thermodynamique ──
        active_power   = self.compute_active_power(
            steam_flow_hp, pressure_hp, temperature_hp, valve_v1, esv_open=esv_open
        )
        turbine_speed  = self.compute_turbine_speed(pressure_hp, valve_v1, valve_bp_admit, esv_open=esv_open)
        pressure_bp    = self.compute_bp_pressure(
            steam_flow_hp, temperature_hp, valve_v1
        )
        temperature_bp = self.compute_bp_temperature(
            temperature_hp, pressure_hp, pressure_bp
        )
        flow_condenser = self.compute_condenser_flow(
            steam_flow_hp, valve_bp, valve_v1
        )
        p_bp_barillet = self.compute_bp_barillet_pressure(steam_flow_hp, valve_v1)        
        efficiency     = self.compute_efficiency(
            active_power, steam_flow_hp, temperature_hp, pressure_hp
        )

        # ── BP Mass Balance (Complet) ──
        bp_dist = self.compute_bp_flow_distribution(
            steam_flow_hp, valve_bp, valve_v1
        )

        # ── Débits hydrauliques par vanne (informatifs) ──
        flow_v1 = steam_flow_hp * 0.80 * (valve_v1 / 100.0)  # T/h
        flow_v2 = steam_flow_hp * 0.07 * (valve_v2 / 100.0)  # T/h
        flow_v3 = steam_flow_hp * 0.07 * (valve_v3 / 100.0)  # T/h

        # ── Bilan énergie ──
        charge_site    = min(active_power, self.CHARGE_SITE_MW)
        excedent_reseau = max(0.0, active_power - self.CHARGE_SITE_MW)

        # ── Électrique (branche AVR dynamique vs formule algébrique legacy) ──
        from core.config import AVR_ENABLED, AVR_Q_SENSITIVITY, Q_TANH_SCALE_MVAR, NOMINAL
        from simulation.avr_controller import avr_controller as _avr
        if AVR_ENABLED and _avr.mode != "OFF":
            e_fd      = _avr.e_fd_pu
            # V_term réagit à E_fd (sensibilité linéaire, ~±5% autour du nominal)
            v_term_kv = round(max(9.0, min(12.0,
                               self.VOLTAGE_KV * (0.95 + 0.05 * e_fd))), 3)
            # cos φ dynamique : consigne AVR courante (évite le hardcode 0.85)
            cosphi_target = float(getattr(_avr, "cosphi_set", NOMINAL["power_factor"]))
            cosphi_target = max(0.70, min(0.99, cosphi_target))
            # q_base=0 si pas de production (SYNCHRONIZING) pour éviter NaN sur tan(acos)
            q_base = active_power * math.tan(math.acos(cosphi_target)) if active_power > 0.1 else 0.0
            # Saturation tanh : régime linéaire pour petites excursions E_fd,
            # saturation douce à ±Q_TANH_SCALE_MVAR pour grandes excursions
            # (remplace l'ancien hard-clamp [-20, +35] MVAR)
            delta_q_raw = AVR_Q_SENSITIVITY * (e_fd - 1.0)
            delta_q_sat = Q_TANH_SCALE_MVAR * math.tanh(delta_q_raw / Q_TANH_SCALE_MVAR)
            q_mvar      = round(q_base + delta_q_sat, 3)
            s_mva     = round(math.sqrt(active_power**2 + q_mvar**2), 3)
            power_factor = round(
                max(0.01, min(1.0, active_power / s_mva)) if s_mva > 0 else 0.85, 3
            )
            elec = {
                "apparent_power":     s_mva,
                "apparent_power_max": 41.0,
                "reactive_power":     q_mvar,
                "current_a":          round((s_mva * 1e6) / (self.SQRT3 * v_term_kv * 1000.0), 1),
                "voltage":            v_term_kv,
            }
        else:
            power_factor = self.compute_power_factor(active_power)
            elec         = self.compute_electrical_signals(active_power, power_factor)

        # ── Mécanique & Auxiliaires ──
        mech = self.compute_mechanical_auxiliaries(turbine_speed, temperature_hp, active_power)

        # ── Gate machine_state : muter les valeurs sans sens à STOPPED/TRIPPED ──
        # Importé ici (évite circular import au module-level)
        try:
            from simulation.controller import controller as _ctrl
            from simulation.avr_controller import avr_controller as _avr_ref
            machine_st = _ctrl.machine_state
            startup_ph = _ctrl.startup_phase
            is_running = machine_st in ("ROLLING", "SYNCHRONIZING", "GRID_CONNECTED")
            # Phase préchauffage : rotor en rotation lente, vapeur BP active mais ESV fermée
            is_warming = (machine_st == "STOPPED"
                          and startup_ph in ("BARRAGE_OPENED", "ESV_OPENED", "V1_OPENING"))
            is_alive   = is_running or is_warming
            is_excited = _avr_ref.mode != "OFF" and _avr_ref.e_fd_pu > 0.1
        except Exception:
            is_running = True   # mode dégradé : ne pas bloquer les calculs
            is_warming = False
            is_alive   = True
            is_excited = True

        if not is_alive:
            # Machine vraiment à l'arrêt (STOPPED+PRE_CHECKS ou TRIPPED) — tout muet
            mech["vib_bearing_fwd"]    = 0.0
            mech["vib_bearing_aft"]    = 0.0
            mech["temp_bearing_fwd"]   = 25.0
            mech["temp_bearing_aft"]   = 25.0
            mech["axial_displacement"] = 0.0
            mech["casing_expansion"]   = 0.0
            mech["grid_frequency"]     = 0.0
            mech["lube_oil_press"]     = 1.2   # pompe AUX maintient ~1.2 bar à l'arrêt
            mech["lube_oil_temp"]      = 25.0
            mech["lube_oil_temp_out"]  = 25.0
            mech["lube_oil_filter_dp"] = 0.0
            efficiency          = 0.0
            p_bp_barillet       = 0.0
            flow_condenser      = 0.0
            bp_dist = {
                "flow_condenseur": 0.0, "flow_barillet_in": 0.0,
                "flow_chauffage_as": 0.0, "flow_surchauffeur": 0.0,
            }
            pressure_condenser_val = 0.0
            active_power    = 0.0
            power_factor    = 0.0
            # Source BP IMACID : alimentation externe toujours disponible même machine trippée
            from core.config import PRESSURE_BP_BARRAGE_BAR
            pressure_bp    = PRESSURE_BP_BARRAGE_BAR   # 4.5 bar — source indépendante de la turbine
            temperature_bp = self.nominal["temperature_bp"]  # ~226 °C — source IMACID
            flow_v1 = flow_v2 = flow_v3 = 0.0
            charge_site     = 0.0
            excedent_reseau = 0.0
        elif is_warming:
            # Phase préchauffage barrage : rotor tourne (~3000 RPM), vapeur BP alimente.
            # Mécanique conservée (vibration, dilatation, paliers calculés depuis turbine_speed).
            # BP entrée = pression alimentation barrage (4.5 bar) tant que bp_admit > 0.
            from core.config import PRESSURE_BP_BARRAGE_BAR
            if valve_bp_admit > 1.0:
                pressure_bp    = PRESSURE_BP_BARRAGE_BAR  # ~4.5 bar alimentation barrage
                temperature_bp = 150.0                    # vapeur de barrage saturée typique
            else:
                pressure_bp    = 1.013
                temperature_bp = 25.0
            # Vide condenseur : 60 % du nominal (évite le 0 brutal qui génère des alarmes)
            pressure_condenser_val = round(self.nominal["pressure_condenser"] * 0.6, 1)
            # Électrique/réseau : muet (contrôlé par is_excited et is_grid_connected plus bas)
            active_power    = 0.0
            power_factor    = 0.0
            p_bp_barillet   = 0.0
            flow_condenser  = 0.0
            bp_dist = {
                "flow_condenseur": 0.0, "flow_barillet_in": 0.0,
                "flow_chauffage_as": 0.0, "flow_surchauffeur": 0.0,
            }
            flow_v1 = flow_v2 = flow_v3 = 0.0
            charge_site     = 0.0
            excedent_reseau = 0.0
        else:
            pressure_condenser_val = self.nominal["pressure_condenser"]
            if valve_bp_admit > 1.0:
                from core.config import PRESSURE_BP_BARRAGE_BAR
                pressure_bp = max(pressure_bp, PRESSURE_BP_BARRAGE_BAR)

        if not is_excited:
            # Pas d'excitation → pas de tension ni de signaux électriques ni de puissance
            elec = {
                "apparent_power":     0.0,
                "apparent_power_max": 41.0,
                "reactive_power":     0.0,
                "current_a":          0.0,
                "voltage":            0.0,
            }
            power_factor    = 0.0
            active_power    = 0.0   # sans excitation : 0 MW injectés réseau
            charge_site     = 0.0
            excedent_reseau = 0.0
        # Avant couplage réseau : turbine excitée mais pas de débit électrique
        try:
            is_grid_connected = _ctrl.machine_state == "GRID_CONNECTED"
        except Exception:
            is_grid_connected = True
        if not is_grid_connected:
            active_power           = 0.0
            elec["reactive_power"] = 0.0
            elec["current_a"]      = 0.0
            elec["apparent_power"] = 0.0
            power_factor           = 0.0
            charge_site            = 0.0
            excedent_reseau        = 0.0
            # voltage conservé : l'AVR produit la tension aux bornes avant couplage
        
        return {
            # Entrées primaires (arrondies)
            "pressure_hp":          round(pressure_hp, 2),
            "temperature_hp":       round(temperature_hp, 1),
            "steam_flow_hp":        round(steam_flow_hp if esv_open else 0.0, 1),
            # BP
            "pressure_bp_in":       round(pressure_bp, 3),
            "temperature_bp":       temperature_bp,
            "steam_flow_bp_in":     steam_flow_bp_in,
            # Sorties vapeur
            "steam_flow_condenser": flow_condenser,
            "pressure_bp_barillet": p_bp_barillet,
            "pressure_condenser":   pressure_condenser_val,
            # Turbine
            "turbine_speed":        turbine_speed,
            # Puissance
            "active_power":         active_power,
            "power_factor":         power_factor,
            "apparent_power":       elec["apparent_power"],
            "reactive_power":       elec["reactive_power"],
            "current_a":            elec["current_a"],
            "voltage":              elec["voltage"],
            # Vannes (sera fusionné avec cibles depuis fake_api)
            "valve_v1": round(valve_v1, 2),
            "valve_v2": round(valve_v2, 2),
            "valve_v3": round(valve_v3, 2),
            "valve_bp": round(valve_bp, 2),
            # Rendement
            "efficiency": efficiency,
            # Nouveaux champs Mass Balance & Énergie
            "flow_v1_th": round(flow_v1, 1),
            "flow_v2_th": round(flow_v2, 1),
            "flow_v3_th": round(flow_v3, 1),
            "flow_barillet_in":    bp_dist["flow_barillet_in"],
            "flow_chauffage_as":   bp_dist["flow_chauffage_as"],
            "flow_surchauffeur":   bp_dist["flow_surchauffeur"],
            # Champ legacy pour compatibilité affichage
            "flow_condenseur":     bp_dist["flow_condenseur"],
            "charge_site":     round(charge_site, 2),
            "excedent_reseau": round(excedent_reseau, 2),
            # Ajouts mécaniques SCADA
            "grid_frequency":     mech["grid_frequency"],
            "vib_bearing_fwd":    mech["vib_bearing_fwd"],
            "vib_bearing_aft":    mech["vib_bearing_aft"],
            "temp_bearing_fwd":   mech["temp_bearing_fwd"],
            "temp_bearing_aft":   mech["temp_bearing_aft"],
            "lube_oil_press":      mech["lube_oil_press"],
            "lube_oil_temp":       mech["lube_oil_temp"],
            "lube_oil_temp_out":   mech["lube_oil_temp_out"],
            "lube_oil_tank_level": mech["lube_oil_tank_level"],
            "lube_oil_pump":       mech["lube_oil_pump"],
            "lube_oil_filter_dp":  mech["lube_oil_filter_dp"],
            "axial_displacement": mech["axial_displacement"],
            "casing_expansion":   mech["casing_expansion"],
        }

    # ──────────────────────────────────────────
    # VALIDATION DU MODÈLE SUR POINTS NOMINAUX
    # ──────────────────────────────────────────

    def validate_nominal(self) -> dict:
        """
        Vérifie que le modèle reproduit les points nominaux spécifiés.
        Utile pour détecter une dérive des coefficients après calibrage.
        Retourne un dict {paramètre: (valeur_calculée, valeur_spec, erreur_%)}
        """
        n = self.nominal
        result = self.compute_all(
            pressure_hp    = n["pressure_hp"],
            temperature_hp = T_HP_DESIGN,
            steam_flow_hp  = n["steam_flow_hp"],
            valve_v1       = 100.0,
            valve_v2       = 100.0,
            valve_v3       = 100.0,
            valve_bp       = n["valve_bp"],
            esv_open       = True,
        )

        checks = {
            "active_power":   (result["active_power"],   24.0,   "MW"),
            "turbine_speed":  (result["turbine_speed"],  6435.0, "RPM"),
            "pressure_bp_in": (result["pressure_bp_in"], 4.5,    "bar"),
            "efficiency":     (result["efficiency"],     92.0,   "%"),
            "current_a":      (result["current_a"],      2254.0, "A"),
        }

        report = {}
        for key, (calc, spec, unit) in checks.items():
            if spec != 0:
                err_pct = abs(calc - spec) / spec * 100
            else:
                err_pct = 0.0
            report[key] = {
                "calculated": round(calc, 3),
                "spec":       spec,
                "unit":       unit,
                "error_pct":  round(err_pct, 2),
                "ok":         err_pct < 5.0,   # tolérance 5%
            }

        return report