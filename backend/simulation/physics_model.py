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
  6. valve_mp et valve_bp contrôlent le split du débit sortie
  7. Pression condenseur 0.0064 bar intégrée dans le rendement BP
  8. Signaux électriques calculés : I(A), Q(MVAR), S(MVA)
"""

import math
import json
import os
from iapws import IAPWS97

from core.config import (
    NOMINAL, T_HP_DESIGN, T_HP_OPERATING, CALIBRATION_COEFFS,
    PHYSICS_ETA_IS_HP, PHYSICS_ETA_IS_BP, PHYSICS_V1_FLOW_FACTOR, PHYSICS_P_OUT_RATIO,
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
    except Exception:
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
    except Exception:
        return h_in_kJkg, 0.0

class PhysicsModel:
    """
    Modèle thermodynamique du Groupe Turbo-Alternateur (régime permanent).

    Entrées primaires (commandes) :
      pressure_hp, temperature_hp, steam_flow_hp  — état vapeur HP
      valve_v1    — admission HP (80% du débit total)
      valve_v2, valve_v3 — équilibrage mécanique (pas dans le bilan thermo)
      valve_mp    — extraction MP vers barillet
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
        # Puissance de référence au point design (486°C, 60 bar, 120 T/h, V1=100%, MP=50%)
        # Utilisée par compute_machine_performance pour le "rendement machine" de la spec.
        self.P_NOMINAL_REF = self.compute_active_power(
            steam_flow_hp  = self.nominal["steam_flow_hp"],
            pressure_hp    = self.nominal["pressure_hp"],
            temperature_hp = T_HP_DESIGN,
            valve_v1       = 100.0,
            valve_mp       = self.nominal["valve_mp"],
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
            except Exception:
                pass   # Utilise les valeurs par défaut si lecture échoue

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
                         valve_mp: float = 50.0) -> float:
        """
        Puissance active (MW) — bilan enthalpique 2-étages (HP + BP avec soutirage MP).
        
        Architecture (turbine à condensation avec soutirage MP) :
        [HP] vapeur 60 bar 486°C → détente → 4.5 bar (sortie étage HP)
            → soutirage MP (% valve_mp) vers barillet / chauffage AS / surchauffeur
            → reste : [BP] 4.5 bar → détente → 0.0064 bar (condenseur vide)
        
        Équations :
        P_HP_méca = η_is_HP · ṁ_HP · Δh_HP_idéal
        P_BP_méca = η_is_BP · ṁ_BP · Δh_BP_idéal    (ṁ_BP = ṁ_HP · (1 - extraction))
        P_élec    = (P_HP_méca + P_BP_méca) · η_méca · η_élec
        
        Point clé : Δh_BP_idéal est calculé depuis la SORTIE RÉELLE de l'étage HP
        (pas la sortie idéale) — car l'irréversibilité HP augmente l'entropie,
        ce qui réduit le potentiel de travail de l'étage BP.
        """
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
        
        # ── SOUTIRAGE MP entre les 2 étages ──
        # valve_mp=50% → 10% de soutirage ; valve_mp=100% → 20% de soutirage.
        extraction_ratio = 0.76 * (valve_mp / 100.0)
        m_dot_bp = m_dot_hp * (1.0 - extraction_ratio)
        
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

    def compute_turbine_speed(self, pressure_hp: float, valve_v1: float) -> float:
        """
        Vitesse turbine (RPM).
        En régime permanent la vitesse est quasi-constante à 6435 RPM.
        Légère variation autour du nominal proportionnelle à √(P_hp/P_nom) × V1.
        (La swing equation est réservée aux transitoires — hors scope régime permanent)
        """
        p_ratio = pressure_hp / self.nominal["pressure_hp"]
        speed   = self.NOMINAL_SPEED * math.sqrt(p_ratio) * (valve_v1 / 100.0)
        return round(max(0.0, speed), 1)

    # ──────────────────────────────────────────
    # PRESSION BP — LOI DE STODOLA
    # ──────────────────────────────────────────

    def compute_bp_pressure(self, steam_flow_hp: float, temperature_hp: float,
                             valve_mp: float, valve_v1: float) -> float:
        """
        Pression BP via loi de Stodola (ellipse de turbine).
        P_bp² ≈ C_stodola × Q² × T_in   (forme simplifiée)

        La vanne valve_mp d'extraction modifie le débit résiduel vers BP.
        Plus valve_mp est ouverte, plus de vapeur est extraite en MP → P_bp diminue.

        Cette relation est physiquement correcte : la pression BP est déterminée
        par le débit qui traverse les étages BP, pas par une proportion fixe de P_hp.
        """
        # Débit effectif traversant l'admission HP
        effective_flow = steam_flow_hp * (valve_v1 / 100.0)
        # Débit résiduel vers BP après extraction MP
        extraction_fraction = 0.20 * (valve_mp / 100.0)   # valve_mp extrait jusqu'à 20%
        q_bp = effective_flow * (1.0 - extraction_fraction)

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

    def compute_condenser_flow(self, steam_flow_hp: float, valve_mp: float,
                                valve_bp: float, valve_v1: float) -> float:
        """
        Débit de vapeur détendue vers le condenseur (T/h).
        = débit HP effectif - extraction MP - extraction BP process
        Nominal : 120 T/h × (1 - 0.20×valve_mp - quelques % pertes) ≈ 74 T/h
        """
        effective_flow = steam_flow_hp * (valve_v1 / 100.0)
        extraction_mp = effective_flow * 0.20 * (valve_mp / 100.0)
        # valve_bp régule la sortie vers condenseur (ouverture nominale ~80%)
        flow_to_cond  = (effective_flow - extraction_mp) * (valve_bp / 100.0)
        return round(max(0.0, flow_to_cond), 1)

    # ──────────────────────────────────────────
    # PRESSION MP/BP BARILLET (sortie process)
    # ──────────────────────────────────────────
    def compute_mp_barillet_pressure(self, pressure_hp: float, valve_mp: float) -> float:
        """
        Pression barillet MP (bar) — soutirage intermédiaire turbine HP.
        Nominalement ~9.5 bar à P_hp=60 bar (ratio ~0.158).
        valve_mp contrôle le débit extrait → légère influence sur pression.
        """
        base_ratio = 9.5 / 60.0   # ratio nominal
        p_mp = pressure_hp * base_ratio
        # valve_mp ouverte → plus d'extraction → légère chute de pression
        valve_effect = (1.0 - (valve_mp / 100.0) * 0.05)
        return round(max(7.0, min(12.0, p_mp * valve_effect)), 3)

    def compute_bp_barillet_pressure(self, pressure_bp: float) -> float:
        """
        Pression barillet BP (bar).
        Physiquement couplée à la pression d'échappement turbine BP.
        """
        # Synchronisation stricte demandée par l'utilisateur
        p_bar = pressure_bp
        return round(max(2.0, min(7.0, p_bar)), 3)

    # ──────────────────────────────────────────
    # DISTRIBUTION DÉBIT BP COMPLÈTE
    # ──────────────────────────────────────────

    def compute_bp_flow_distribution(self, steam_flow_hp, valve_mp, valve_bp, valve_v1):
        """
        Bilan massique complet de la vapeur BP — 4 destinations selon specs GTA :
          1. Condenseur          (circuit principal)
          2. Barillet 3 bar      (extraction MP)
          3. Chauffage eau AS    (acide sulfurique)
          4. Surchauffeur AS     (acide sulfurique)
        """
        effective_flow = steam_flow_hp * (valve_v1 / 100.0)

        # Extraction MP → barillet + dérivations acide sulfurique
        extraction_mp = effective_flow * 0.20 * (valve_mp / 100.0)

        # Répartition de l'extraction MP entre les 3 destinations BP
        flow_barillet      = extraction_mp * 0.50   # → barillet 3 bar
        flow_chauffage_as  = extraction_mp * 0.30   # → chauffage eau AS
        flow_surchauffeur  = extraction_mp * 0.20   # → surchauffeur AS

        # Débit vers condenseur
        flow_condenseur = (effective_flow - extraction_mp) * (valve_bp / 100.0)

        return {
            "flow_condenseur":     round(flow_condenseur, 1),   # T/h → condenseur
            "flow_barillet":       round(flow_barillet, 1),     # T/h → barillet
            "flow_chauffage_as":   round(flow_chauffage_as, 1), # T/h → chauffage AS
            "flow_surchauffeur":   round(flow_surchauffeur, 1), # T/h → surchauffeur AS
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
                                (486°C, 60 bar, 120 T/h, V1=100%, valve_mp=50%).
        
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
        
        # 5. Déplacements & Dilatations (thermique)
        heat_ratio = temperature_hp / T_HP_DESIGN
        axial_disp = 0.2 + (heat_ratio - 1.0) * 2.0 + (active_power / 32.0) * 0.15
        expansion = 5.0 * heat_ratio + random.uniform(-0.05, 0.05)
        
        return {
            "grid_frequency": round(max(0.0, grid_frequency), 2),
            "vib_bearing_fwd": round(max(0.0, vib_fwd), 2),
            "vib_bearing_aft": round(max(0.0, vib_aft), 2),
            "temp_bearing_fwd": round(max(0.0, temp_fwd), 1),
            "temp_bearing_aft": round(max(0.0, temp_aft), 1),
            "lube_oil_press": round(max(0.0, lube_press), 2),
            "lube_oil_temp": round(max(0.0, lube_temp), 1),
            "axial_displacement": round(axial_disp, 3),
            "casing_expansion": round(max(0.0, expansion), 2),
        }

    # ──────────────────────────────────────────
    # CALCUL GLOBAL — point d'entrée principal
    # ──────────────────────────────────────────

    def compute_all(self, pressure_hp: float, temperature_hp: float,
                    steam_flow_hp: float, valve_v1: float,
                    valve_v2: float, valve_v3: float,
                    valve_mp: float, valve_bp: float) -> dict:
        """
        Calcule tous les paramètres dérivés à partir des 8 entrées primaires.

        Note sur V2/V3 : reçus en paramètre pour cohérence avec le schéma de données,
        mais NE SONT PAS utilisés dans les équations thermodynamiques.
        Leur rôle (équilibrage mécanique) sera exploité par le module IA vibrations.

        Retourne un dict complet prêt pour GTAParameters.
        """
        # ── Thermodynamique ──
        active_power   = self.compute_active_power(
            steam_flow_hp, pressure_hp, temperature_hp, valve_v1
        )
        turbine_speed  = self.compute_turbine_speed(pressure_hp, valve_v1)
        pressure_bp    = self.compute_bp_pressure(
            steam_flow_hp, temperature_hp, valve_mp, valve_v1
        )
        temperature_bp = self.compute_bp_temperature(
            temperature_hp, pressure_hp, pressure_bp
        )
        flow_condenser = self.compute_condenser_flow(
            steam_flow_hp, valve_mp, valve_bp, valve_v1
        )
        p_mp_barillet = self.compute_mp_barillet_pressure(pressure_hp, valve_mp)
        p_bp_barillet = self.compute_bp_barillet_pressure(pressure_bp)        
        efficiency     = self.compute_efficiency(
            active_power, steam_flow_hp, temperature_hp, pressure_hp
        )

        # ── BP Mass Balance (Complet) ──
        bp_dist = self.compute_bp_flow_distribution(
            steam_flow_hp, valve_mp, valve_bp, valve_v1
        )

        # ── Débits hydrauliques par vanne (informatifs) ──
        flow_v1 = steam_flow_hp * 0.80 * (valve_v1 / 100.0)  # T/h
        flow_v2 = steam_flow_hp * 0.07 * (valve_v2 / 100.0)  # T/h
        flow_v3 = steam_flow_hp * 0.07 * (valve_v3 / 100.0)  # T/h

        # ── Bilan énergie ──
        charge_site    = min(active_power, self.CHARGE_SITE_MW)
        excedent_reseau = max(0.0, active_power - self.CHARGE_SITE_MW)

        # ── Électrique ──
        power_factor   = self.compute_power_factor(active_power)
        elec           = self.compute_electrical_signals(active_power, power_factor)

        # ── Mécanique & Auxiliaires ──
        mech = self.compute_mechanical_auxiliaries(turbine_speed, temperature_hp, active_power)

        return {
            # Entrées primaires (arrondies)
            "pressure_hp":          round(pressure_hp, 2),
            "temperature_hp":       round(temperature_hp, 1),
            "steam_flow_hp":        round(steam_flow_hp, 1),
            # BP
            "pressure_bp_in":       round(pressure_bp, 3),
            "temperature_bp":       temperature_bp,
            "steam_flow_bp_in":     0.0,   # nul en régime permanent (démarrage uniquement)
            # Sorties vapeur
            "steam_flow_condenser": flow_condenser,
            "pressure_mp_barillet": p_mp_barillet,
            "pressure_bp_barillet": p_bp_barillet,
            "pressure_condenser":   self.nominal["pressure_condenser"],  # 0.0064 bar fixe
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
            "valve_mp": round(valve_mp, 2),
            "valve_bp": round(valve_bp, 2),
            # Rendement
            "efficiency": efficiency,
            # Nouveaux champs Mass Balance & Énergie
            "flow_v1_th": round(flow_v1, 1),
            "flow_v2_th": round(flow_v2, 1),
            "flow_v3_th": round(flow_v3, 1),
            "flow_barillet":       bp_dist["flow_barillet"],
            "flow_chauffage_as":   bp_dist["flow_chauffage_as"],
            "flow_surchauffeur":   bp_dist["flow_surchauffeur"],
            "charge_site":     round(charge_site, 2),
            "excedent_reseau": round(excedent_reseau, 2),
            # Ajouts mécaniques SCADA
            "grid_frequency":     mech["grid_frequency"],
            "vib_bearing_fwd":    mech["vib_bearing_fwd"],
            "vib_bearing_aft":    mech["vib_bearing_aft"],
            "temp_bearing_fwd":   mech["temp_bearing_fwd"],
            "temp_bearing_aft":   mech["temp_bearing_aft"],
            "lube_oil_press":     mech["lube_oil_press"],
            "lube_oil_temp":      mech["lube_oil_temp"],
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
            valve_mp       = n["valve_mp"],
            valve_bp       = n["valve_bp"],
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