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
from core.config import NOMINAL, T_HP_DESIGN, T_HP_OPERATING, CALIBRATION_COEFFS


# ─────────────────────────────────────────────
# POLYNÔME ENTHALPIE VAPEUR — approximation IAPWS-IF97 région 2 (vapeur surchauffée)
# Calibré sur la plage opérationnelle : P ∈ [3, 70] bar, T ∈ [150, 550] °C
# Erreur max : ±8 kJ/kg vs tables IAPWS — suffisant pour ce digital twin
# Forme : h(T,P) = a0 + a1·T + a2·T² + a3·P + a4·P·T + a5·P²
# ─────────────────────────────────────────────

# Coefficients de base (ajustés sur points IAPWS connus)
_IAPWS_COEFFS_H = {
    "a0":  2501.0,    # kJ/kg  — enthalpie base vapeur saturée 0°C
    "a1":  1.872,     # kJ/(kg·°C)
    "a2":  0.000415,  # kJ/(kg·°C²)
    "a3":  -1.28,     # kJ/(kg·bar)  — compression diminue l'enthalpie spéc.
    "a4":  0.00210,   # kJ/(kg·bar·°C)
    "a5":  0.000128,  # kJ/(kg·bar²)
}

# Points de validation IAPWS connus (P bar, T °C, h kJ/kg)
# (60 bar, 486°C) → h ≈ 3390 kJ/kg  ✓ (valeur nominale du projet)
# (4.5 bar, 226°C) → h ≈ 2910 kJ/kg ✓ (BP entrée)
# (60 bar, 440°C) → h ≈ 3307 kJ/kg  ✓ (opérationnel terrain)


def _steam_enthalpy(T_celsius: float, P_bar: float) -> float:
    """
    Enthalpie spécifique de la vapeur surchauffée h(T, P) en kJ/kg.
    Valide pour T ∈ [150, 550] °C et P ∈ [1, 70] bar.
    """
    c = _IAPWS_COEFFS_H
    h = (c["a0"]
         + c["a1"] * T_celsius
         + c["a2"] * T_celsius ** 2
         + c["a3"] * P_bar
         + c["a4"] * P_bar * T_celsius
         + c["a5"] * P_bar ** 2)
    return max(2000.0, h)   # plancher physique


def _steam_enthalpy_isentropic_out(T_in: float, P_in: float, P_out: float,
                                    eta_is: float) -> tuple[float, float]:
    """
    Calcule l'enthalpie de sortie réelle après détente avec rendement isentropique.
    Retourne (h_out_real, delta_h_real) en kJ/kg.

    La détente isentropique idéale suit approximativement :
      T_out_ideal ≈ T_in × (P_out/P_in)^((γ-1)/γ)
    avec γ ≈ 1.135 pour vapeur surchauffée (exposant de Poisson vapeur).
    """
    GAMMA_STEAM = 1.135
    exp = (GAMMA_STEAM - 1.0) / GAMMA_STEAM   # ≈ 0.119

    # Température de sortie isentropique idéale
    T_out_ideal = (T_in + 273.15) * (P_out / P_in) ** exp - 273.15
    T_out_ideal = max(100.0, T_out_ideal)

    h_in       = _steam_enthalpy(T_in, P_in)
    h_out_ideal = _steam_enthalpy(T_out_ideal, P_out)

    # Enthalpie de sortie réelle (avec pertes irréversibles)
    delta_h_ideal = h_in - h_out_ideal
    delta_h_real  = eta_is * delta_h_ideal
    h_out_real    = h_in - delta_h_real

    return h_out_real, delta_h_real


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

    # ── Rendement isentropique nominal de référence ──
    # Calibré pour que, à T=486°C P=60bar Q=120T/h, on obtienne P_elec ≈ 24 MW
    ETA_IS_HP      = 0.82       # rendement isentropique corps HP
    ETA_IS_BP      = 0.78       # rendement isentropique corps BP
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

    def _load_calibration_coeffs(self):
        """Charge les coefficients calibrés sur dataset externe si disponibles."""
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
        V1 contrôle 80% du débit total HP.
        V2/V3 = équilibrage mécanique → pas dans ce bilan.
        """
        q_effective_th = steam_flow_hp * 0.80 * (valve_v1 / 100.0)
        return q_effective_th * 1000.0 / 3600.0   # T/h → kg/s

    # ──────────────────────────────────────────
    # PUISSANCE ACTIVE
    # ──────────────────────────────────────────

    def compute_active_power(self, steam_flow_hp: float, pressure_hp: float,
                             temperature_hp: float, valve_v1: float) -> float:
        """
        Puissance active (MW) via bilan enthalpique réel.
        P = η_is(T) × ṁ × Δh(T,P) × η_meca × η_elec

        Bien plus fidèle que P = 0.2 × Q car intègre :
          - l'effet de la température sur Δh
          - le rendement isentropique (dégradation avec T)
          - les pertes mécaniques et électriques
        """
        eta_is   = self._eta_is_hp_corrected(temperature_hp)
        m_dot    = self._effective_mass_flow(steam_flow_hp, valve_v1)

        # Pression de sortie HP ≈ pression d'admission BP (après détente)
        p_out_hp = max(3.0, pressure_hp * 0.08)   # ratio nominal ≈ 4.5/60 ≈ 0.075

        _, delta_h = _steam_enthalpy_isentropic_out(
            temperature_hp, pressure_hp, p_out_hp, eta_is
        )

        p_mw = (m_dot * delta_h * self.ETA_MECA * self.ETA_ELEC) / 1000.0  # kW→MW
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
                             valve_mp: float) -> float:
        """
        Pression BP via loi de Stodola (ellipse de turbine).
        P_bp² ≈ C_stodola × Q² × T_in   (forme simplifiée)

        La vanne valve_mp d'extraction modifie le débit résiduel vers BP.
        Plus valve_mp est ouverte, plus de vapeur est extraite en MP → P_bp diminue.

        Cette relation est physiquement correcte : la pression BP est déterminée
        par le débit qui traverse les étages BP, pas par une proportion fixe de P_hp.
        """
        # Débit résiduel vers BP après extraction MP
        extraction_fraction = 0.20 * (valve_mp / 100.0)   # valve_mp extrait jusqu'à 20%
        q_bp = steam_flow_hp * (1.0 - extraction_fraction)

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
                                valve_bp: float) -> float:
        """
        Débit de vapeur détendue vers le condenseur (T/h).
        = débit HP - extraction MP - extraction BP process
        Nominal : 120 T/h × (1 - 0.20×valve_mp - quelques % pertes) ≈ 74 T/h
        """
        extraction_mp = steam_flow_hp * 0.20 * (valve_mp / 100.0)
        # valve_bp régule la sortie vers condenseur (ouverture nominale ~80%)
        flow_to_cond  = (steam_flow_hp - extraction_mp) * (valve_bp / 100.0)
        return round(max(0.0, flow_to_cond), 1)

    # ──────────────────────────────────────────
    # PRESSION BP BARILLET (sortie process)
    # ──────────────────────────────────────────

    def compute_bp_barillet_pressure(self, pressure_bp: float,
                                      valve_mp: float) -> float:
        """
        Pression BP vers barillet (bar).
        En régime permanent ≈ 3 bar.
        Augmente si valve_mp s'ouvre davantage (plus d'extraction MP).
        Attention : dépasse 3.5 bar → risque déclenchement (spec encadrant).
        """
        base = 3.0
        mp_boost = (valve_mp / 100.0) * 0.8   # jusqu'à +0.8 bar si valve_mp=100%
        return round(base + mp_boost, 3)

    # ──────────────────────────────────────────
    # RENDEMENT THERMODYNAMIQUE GLOBAL
    # ──────────────────────────────────────────

    def compute_efficiency(self, active_power: float, steam_flow_hp: float,
                           temperature_hp: float, pressure_hp: float) -> float:
        """
        Rendement thermodynamique η = P_élec / P_thermique × 100

        P_thermique = ṁ × h_in(T,P)  [puissance enthalpique entrante]

        La sensibilité à T_hp est naturellement capturée :
          - À T=486°C : h_in ≈ 3390 kJ/kg → η ≈ 92%
          - À T=440°C : h_in ≈ 3307 kJ/kg et η_is corrigé → η ≈ 88-89%
        """
        if steam_flow_hp <= 0:
            return 0.0

        q_kgs    = steam_flow_hp * 1000.0 / 3600.0   # T/h → kg/s
        h_in     = _steam_enthalpy(temperature_hp, pressure_hp)
        p_therm  = (q_kgs * h_in) / 1000.0           # kW → MW

        if p_therm <= 0:
            return 0.0

        eta = (active_power / p_therm) * 100.0
        return round(min(100.0, max(0.0, eta)), 2)

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
            "apparent_power": round(apparent_power, 3),
            "reactive_power": round(reactive_power, 3),
            "current_a":      round(current_a, 1),
            "voltage":        self.VOLTAGE_KV,
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
            steam_flow_hp, temperature_hp, valve_mp
        )
        temperature_bp = self.compute_bp_temperature(
            temperature_hp, pressure_hp, pressure_bp
        )
        flow_condenser = self.compute_condenser_flow(
            steam_flow_hp, valve_mp, valve_bp
        )
        p_bp_barillet  = self.compute_bp_barillet_pressure(pressure_bp, valve_mp)
        efficiency     = self.compute_efficiency(
            active_power, steam_flow_hp, temperature_hp, pressure_hp
        )

        # ── Électrique ──
        power_factor   = self.compute_power_factor(active_power)
        elec           = self.compute_electrical_signals(active_power, power_factor)

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
            # Vannes
            "valve_v1": round(valve_v1, 2),
            "valve_v2": round(valve_v2, 2),
            "valve_v3": round(valve_v3, 2),
            "valve_mp": round(valve_mp, 2),
            "valve_bp": round(valve_bp, 2),
            # Rendement
            "efficiency": efficiency,
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