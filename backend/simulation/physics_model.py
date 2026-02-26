"""
simulation/physics_model.py — Modèle physique simplifié du GTA
Implémente les équations thermodynamiques reliant les paramètres entre eux.
C'est le cœur du projet : tout le reste s'appuie sur ce fichier.
"""

import math
from core.config import NOMINAL


class PhysicsModel:
    """
    Modèle thermodynamique simplifié du Groupe Turbo-Alternateur.

    Relations physiques implémentées :
      - Puissance active  P (MW) ≈ 0.2 × Q_hp (T/h)
      - Vitesse turbine   N (RPM) ∝ √(P_hp / P_nominal)  × N_nominal
      - Pression BP       P_bp ≈ P_hp × (1 - η_détente)
      - Température BP    T_bp = f(T_hp, rapport de détente)
      - Débit BP          Q_bp ≈ Q_hp × 0.617  (cogénération ≈ 38% utilisé)
      - Rendement         η = P_elec / P_thermique_entree × 100
      - Facteur puissance cos φ ≈ 0.85 ± légère variation avec charge
    """

    # Constantes physiques du GTA (spécifications du rapport)
    GEAR_RATIO        = 4.29        # rapport réducteur turbine/alternateur
    SYNC_SPEED        = 1500.0      # RPM alternateur (50 Hz, 4 pôles)
    NOMINAL_SPEED     = 6435.0      # RPM turbine nominale
    MAX_POWER         = 32.0        # MW
    COGENE_RATIO      = 0.617       # fraction vapeur vers condenseur
    ENTHALPY_DROP     = 800.0       # kJ/kg — chute enthalpique nominale HP→BP
    STEAM_ENTHALPY_IN = 3_390.0     # kJ/kg — enthalpie vapeur HP (60 bar, 486°C)

    def __init__(self):
        self.nominal = NOMINAL.copy()

    # ──────────────────────────────────────────
    # CALCULS PRINCIPAUX
    # ──────────────────────────────────────────

    def compute_active_power(self, steam_flow_hp: float, valve_v1: float) -> float:
        """
        Puissance active (MW) = 0.2 × Q_hp (T/h) × ouverture V1
        Relation empirique validée pour ce type de GTA.
        """
        effective_flow = steam_flow_hp * (valve_v1 / 100.0)
        return round(0.2 * effective_flow, 3)

    def compute_turbine_speed(self, pressure_hp: float, valve_v1: float) -> float:
        """
        Vitesse turbine (RPM) proportionnelle à la racine du rapport de pression.
        Chute de pression → chute de vitesse.
        """
        p_ratio = pressure_hp / self.nominal["pressure_hp"]
        speed   = self.nominal["turbine_speed"] * math.sqrt(p_ratio) * (valve_v1 / 100.0)
        return round(max(0.0, speed), 1)

    def compute_bp_pressure(self, pressure_hp: float, valve_v3: float) -> float:
        """
        Pression BP : détente isentropique simplifiée.
        P_bp = P_hp × (valve_v3/100) × facteur_détente
        """
        expansion_factor = 0.075   # rapport P_bp/P_hp nominal (4.5 / 60)
        return round(pressure_hp * expansion_factor * (valve_v3 / 100.0) * 1.02, 2)

    def compute_bp_temperature(self, temperature_hp: float, pressure_hp: float,
                               pressure_bp: float) -> float:
        """
        Température BP dépendant principalement du rapport de pression.
        Calibré pour que, en conditions nominales, T_bp ≈ NOMINAL["temperature_bp"]
        et diminue lorsque le rapport P_bp / P_hp diminue.
        """
        if pressure_hp <= 0 or pressure_bp <= 0:
            return self.nominal["temperature_bp"]

        # Rapport de pression actuel vs nominal
        nominal_ratio = self.nominal["pressure_bp"] / self.nominal["pressure_hp"]
        ratio         = max(0.01, pressure_bp / pressure_hp)
        # Exposant doux pour éviter des variations trop extrêmes
        exponent      = 0.25

        # À ratio = nominal_ratio → T_bp ≈ temperature_bp_nominale
        scale    = (ratio / nominal_ratio) ** exponent
        temp_bp  = self.nominal["temperature_bp"] * scale

        # Plancher physique minimal
        return round(max(150.0, temp_bp), 1)

    def compute_steam_flow_bp(self, steam_flow_hp: float, valve_v2: float) -> float:
        """
        Débit BP = débit HP × COGENE_RATIO, modifié par l'ouverture de V2.
        V2 contrôle l'extraction intermédiaire (MP).
        """
        extraction_mp = steam_flow_hp * (1 - valve_v2 / 100.0) * 0.15
        flow_bp = steam_flow_hp * self.COGENE_RATIO - extraction_mp
        return round(max(0.0, flow_bp), 1)

    def compute_efficiency(self, active_power: float, steam_flow_hp: float,
                           temperature_hp: float) -> float:
        """
        Rendement thermodynamique η = P_élec / P_thermique_entrée × 100
        P_thermique = Q_hp (kg/s) × Δh (kJ/kg)
        """
        if steam_flow_hp <= 0:
            return 0.0
        q_kgs          = steam_flow_hp * 1000.0 / 3600.0   # T/h → kg/s
        # Enthalpie corrigée par la température
        temp_correction = (temperature_hp - self.nominal["temperature_hp"]) * 1.5
        delta_h         = self.ENTHALPY_DROP + temp_correction
        p_thermal_mw    = (q_kgs * delta_h) / 1000.0       # kW → MW
        if p_thermal_mw <= 0:
            return 0.0
        eta = (active_power / p_thermal_mw) * 100.0
        return round(min(100.0, max(0.0, eta)), 2)

    def compute_power_factor(self, active_power: float) -> float:
        """
        Facteur de puissance légèrement variable avec la charge.
        Diminue sous charge partielle, optimal à pleine charge.
        """
        load_ratio  = active_power / self.nominal["active_power"]
        cos_phi     = 0.85 * (0.9 + 0.1 * min(load_ratio, 1.0))
        return round(min(0.99, max(0.70, cos_phi)), 3)

    # ──────────────────────────────────────────
    # CALCUL GLOBAL
    # ──────────────────────────────────────────

    def compute_all(self, pressure_hp: float, temperature_hp: float,
                    steam_flow_hp: float, valve_v1: float,
                    valve_v2: float, valve_v3: float) -> dict:
        """
        Calcule tous les paramètres dérivés à partir des entrées primaires.
        Retourne un dictionnaire complet prêt pour GTAParameters.
        """
        active_power   = self.compute_active_power(steam_flow_hp, valve_v1)
        turbine_speed  = self.compute_turbine_speed(pressure_hp, valve_v1)
        pressure_bp    = self.compute_bp_pressure(pressure_hp, valve_v3)
        temperature_bp = self.compute_bp_temperature(temperature_hp, pressure_hp, pressure_bp)
        steam_flow_bp  = self.compute_steam_flow_bp(steam_flow_hp, valve_v2)
        efficiency     = self.compute_efficiency(active_power, steam_flow_hp, temperature_hp)
        power_factor   = self.compute_power_factor(active_power)

        return {
            "pressure_hp":    round(pressure_hp, 2),
            "temperature_hp": round(temperature_hp, 1),
            "steam_flow_hp":  round(steam_flow_hp, 1),
            "pressure_bp":    pressure_bp,
            "temperature_bp": temperature_bp,
            "steam_flow_bp":  steam_flow_bp,
            "turbine_speed":  turbine_speed,
            "active_power":   active_power,
            "power_factor":   power_factor,
            "efficiency":     efficiency,
            "valve_v1":       valve_v1,
            "valve_v2":       valve_v2,
            "valve_v3":       valve_v3,
        }