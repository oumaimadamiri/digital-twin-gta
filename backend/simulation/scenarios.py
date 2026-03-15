"""
simulation/scenarios.py — 10 scénarios de perturbation du GTA
Mis à jour :
  - V2/V3 retirés des deltas thermo (équilibrage mécanique pur)
  - valve_mp et valve_bp ajoutés là où pertinent
  - Scénario 8 : dépassement 24 MW → surpression BP barillet
  - Scénario 9 : interruption source vapeur (acide sulfurique)
  - Scénario 10 : panne pompe refroidissement huile de graissage
"""

from models.scenario import Scenario

SCENARIOS: dict[int, Scenario] = {

    1: Scenario(
        id=1,
        name="Chute de pression HP",
        description=(
            "Baisse progressive de la pression vapeur HP (fuite ou défaut vanne amont). "
            "Entraîne une chute de puissance, de vitesse turbine et de rendement."
        ),
        perturbation_type="ramp",
        target_deltas={
            "pressure_hp":   -15.0,   # bar  → descend à ~45 bar (seuil alarme 55)
            "steam_flow_hp": -30.0,   # T/h  → débit réduit à ~90 T/h
        },
        duration_s=120,
    ),

    2: Scenario(
        id=2,
        name="Surchauffe vapeur HP",
        description=(
            "Élévation anormale de la température HP au-delà de 500°C. "
            "Risque de fatigue thermique des ailettes. Le rendement augmente "
            "légèrement mais les contraintes dépassent les limites admissibles."
        ),
        perturbation_type="ramp",
        target_deltas={
            "temperature_hp": +40.0,   # °C → monte à ~526°C (seuil critique 500)
        },
        duration_s=90,
    ),

    3: Scenario(
        id=3,
        name="Fermeture partielle vanne V1",
        description=(
            "Restriction de l'admission vapeur HP. Simule un défaut mécanique "
            "ou une commande erronée du système DEH. V1 passe de 100% à 60%. "
            "Puissance et vitesse chutent proportionnellement."
        ),
        perturbation_type="step",
        target_deltas={
            "valve_v1": -40.0,    # % → V1 passe à 60% (adm. HP réduite)
        },
        duration_s=60,
    ),

    4: Scenario(
        id=4,
        name="Perte de charge brutale",
        description=(
            "Délestage soudain du réseau électrique. Puissance chute à ~5 MW, "
            "emballement transitoire possible de la turbine. "
            "Scénario de protection le plus critique."
        ),
        perturbation_type="step",
        target_deltas={
            "steam_flow_hp": -100.0,  # T/h → débit très réduit (~20 T/h)
            "pressure_hp":   -10.0,   # bar
        },
        duration_s=45,
    ),

    5: Scenario(
        id=5,
        name="Dégradation progressive du rendement",
        description=(
            "Encrassement graduel des ailettes turbine ou dégradation des joints. "
            "Rendement diminue lentement : plus de vapeur consommée pour même puissance. "
            "Reproduit la situation terrain actuelle (T=440°C vs design 486°C)."
        ),
        perturbation_type="ramp",
        target_deltas={
            "steam_flow_hp":  +10.0,  # T/h → plus de vapeur nécessaire
            "temperature_hp":  -8.0,  # °C  → légère perte de température
        },
        duration_s=300,
    ),

    6: Scenario(
        id=6,
        name="Oscillations de pression (instabilité DEH)",
        description=(
            "Instabilité du régulateur DEH provoquant des oscillations périodiques "
            "de pression et de vitesse. Période ≈ 10s. "
            "Peut induire des vibrations excessives sur le rotor."
        ),
        perturbation_type="oscillation",
        target_deltas={
            "pressure_hp":   5.0,    # bar  amplitude oscillation (±5 bar)
            # Vitesse turbine oscillera en cascade via compute_turbine_speed
        },
        duration_s=180,
    ),

    7: Scenario(
        id=7,
        name="Défaut alternateur (cos φ dégradé)",
        description=(
            "Problème d'excitation de l'alternateur entraînant une chute "
            "du facteur de puissance en dehors de la plage 0.82–0.86. "
            "Instabilité tension/réactif, risque de désynchronisation."
        ),
        perturbation_type="step",
        target_deltas={
            "power_factor_offset": -0.08,   # cos φ → ~0.77 (traité dans FakeAPI)
        },
        duration_s=90,
    ),

    8: Scenario(
        id=8,
        name="Dépassement puissance → surpression BP barillet",
        description=(
            "Montée en puissance au-delà de 24 MW (vers 28-30 MW). "
            "Augmentation du débit vapeur HP → surpression sur la ligne BP vers barillet. "
            "Risque de déclenchement automatique. Spec : trip à 30 MW."
        ),
        perturbation_type="ramp",
        target_deltas={
            "steam_flow_hp": +35.0,   # T/h → monte à ~155 T/h → P > 24 MW
            "pressure_hp":   +4.0,    # bar  → légère montée pression amont
            "valve_mp":      +25.0,   # % → valve_mp s'ouvre → pression barillet monte
        },
        duration_s=90,
    ),

    9: Scenario(
        id=9,
        name="Interruption source vapeur (acide sulfurique)",
        description=(
            "Arrêt de l'unité de production d'acide sulfurique qui fournit la vapeur HP. "
            "Chute brutale du débit vapeur entrant. "
            "Provoque un déclenchement si la pression HP tombe sous 55 bar."
        ),
        perturbation_type="step",
        target_deltas={
            "steam_flow_hp": -80.0,   # T/h → chute à ~40 T/h (source principale coupée)
            "pressure_hp":   -18.0,   # bar  → descend rapidement sous le seuil d'alarme
            "temperature_hp": -20.0,  # °C   → refroidissement transitoire
        },
        duration_s=60,
    ),

    10: Scenario(
        id=10,
        name="Panne pompe refroidissement huile de graissage",
        description=(
            "Défaillance de la pompe eau de Norya pour le refroidissement de l'huile. "
            "Montée en température des paliers → vibrations → déclenchement de protection. "
            "Condition initiale de démarrage compromise. "
            "Modélisé par une dégradation progressive du rendement mécanique."
        ),
        perturbation_type="ramp",
        target_deltas={
            # Sans refroidissement huile : échauffement → pertes mécaniques augmentent
            # On simule via réduction débit (la turbine réduit charge par protection)
            "steam_flow_hp":  -20.0,  # T/h  → réduction préventive par régulateur
            "pressure_hp":     -5.0,  # bar   → conséquence de la réduction de charge
            # Effet sur l'huile de commande → vannes réagissent moins vite
            "valve_v1":        -8.0,  # %     → légère restriction de sécurité
        },
        duration_s=180,
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