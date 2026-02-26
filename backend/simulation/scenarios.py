"""
simulation/scenarios.py — Définition des 7 scénarios de perturbation du GTA
Chaque scénario modifie les paramètres primaires (entrées du physics_model).
"""

from models.scenario import Scenario

# ─────────────────────────────────────────────
# DÉFINITION DES 7 SCÉNARIOS
# ─────────────────────────────────────────────

SCENARIOS: dict[int, Scenario] = {

    1: Scenario(
        id=1,
        name="Chute de pression HP",
        description="Baisse progressive de la pression vapeur HP (fuite ou défaut vanne amont). "
                    "Entraîne une chute de puissance et de vitesse turbine.",
        perturbation_type="ramp",
        target_deltas={
            "pressure_hp":    -8.0,    # bar  → descend à ~52 bar
            "steam_flow_hp":  -15.0,   # T/h  → débit réduit
        },
        duration_s=120,
    ),

    2: Scenario(
        id=2,
        name="Surchauffe vapeur HP",
        description="Élévation anormale de la température HP au-delà de 500°C. "
                    "Risque de fatigue thermique des ailettes.",
        perturbation_type="ramp",
        target_deltas={
            "temperature_hp": +20.0,   # °C  → monte à ~506°C (seuil critique)
        },
        duration_s=90,
    ),

    3: Scenario(
        id=3,
        name="Fermeture partielle vanne V1",
        description="Restriction de l'admission vapeur HP. Simule un défaut mécanique "
                    "ou une commande erronée du système DEH.",
        perturbation_type="step",
        target_deltas={
            "valve_v1": -40.0,         # %   → V1 passe à 60%
        },
        duration_s=60,
    ),

    4: Scenario(
        id=4,
        name="Perte de charge brutale",
        description="Délestage soudain du réseau électrique. La puissance chute à ~5 MW, "
                    "emballement transitoire possible de la turbine.",
        perturbation_type="step",
        target_deltas={
            "steam_flow_hp":  -80.0,   # T/h  → débit très réduit
            "pressure_hp":    -5.0,
        },
        duration_s=45,
    ),

    5: Scenario(
        id=5,
        name="Dégradation progressive du rendement",
        description="Encrassement graduel des ailettes turbine ou dégradation du joint. "
                    "Rendement diminue lentement sur plusieurs heures.",
        perturbation_type="ramp",
        target_deltas={
            "steam_flow_hp": +10.0,    # T/h  → plus de vapeur pour même puissance
            "temperature_hp": -8.0,
        },
        duration_s=300,
    ),

    6: Scenario(
        id=6,
        name="Oscillations de pression",
        description="Instabilité du régulateur DEH provoquant des oscillations périodiques "
                    "de pression et de vitesse.",
        perturbation_type="oscillation",
        target_deltas={
            "pressure_hp":   5.0,      # amplitude oscillation (±5 bar)
            "turbine_speed": 80.0,     # amplitude oscillation (±80 RPM)
        },
        duration_s=180,
    ),

    7: Scenario(
        id=7,
        name="Défaut alternateur (cos φ dégradé)",
        description="Problème d'excitation de l'alternateur entraînant une chute "
                    "du facteur de puissance et une instabilité tension/réactif.",
        perturbation_type="step",
        target_deltas={
            "power_factor_offset": -0.10,  # cos φ → ~0.75 (traité dans FakeAPI)
        },
        duration_s=90,
    ),
}


def get_all_scenarios() -> list[dict]:
    """Retourne la liste de tous les scénarios (sans les champs internes)."""
    return [
        {
            "id":               s.id,
            "name":             s.name,
            "description":      s.description,
            "perturbation_type": s.perturbation_type,
            "duration_s":       s.duration_s,
        }
        for s in SCENARIOS.values()
    ]


def get_scenario(scenario_id: int) -> Scenario | None:
    return SCENARIOS.get(scenario_id)