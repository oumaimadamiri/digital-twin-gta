"""
simulation/fake_api.py — Générateur de données capteurs (toutes les 500ms)
Simule le comportement dynamique du GTA en l'absence de capteurs physiques.
Tourne en tâche de fond (asyncio) dès le démarrage du serveur.
"""

import asyncio
import math
import random
import time
from datetime import datetime

from core.config import NOMINAL, NOISE_LEVEL, FAKE_API_INTERVAL_MS
from models.gta_parameters import GTAParameters, StatusEnum
from simulation.physics_model import PhysicsModel
from simulation.scenarios import get_scenario, Scenario


class FakeAPI:
    """
    Générateur de données simulées pour le GTA.
    Maintient l'état courant et applique les perturbations de scénario.
    """

    def __init__(self):
        self.physics = PhysicsModel()
        self._running = False

        # État courant des paramètres primaires (modifiables)
        self._state = {
            "pressure_hp":    NOMINAL["pressure_hp"],
            "temperature_hp": NOMINAL["temperature_hp"],
            "steam_flow_hp":  NOMINAL["steam_flow_hp"],
            "valve_v1":       NOMINAL["valve_v1"],
            "valve_v2":       NOMINAL["valve_v2"],
            "valve_v3":       NOMINAL["valve_v3"],
        }

        # Scénario actif
        self._active_scenario: Scenario | None = None
        self._scenario_start_time: float | None = None
        self._oscillation_t: float = 0.0

        # Historique des scénarios déclenchés
        self._scenario_history: list[dict] = []

        # Offset cos φ (scénario 7)
        self._power_factor_offset: float = 0.0

        # Dernier snapshot calculé
        self._last_params: GTAParameters | None = None

        # Callback appelé à chaque nouveau snapshot
        self._on_new_data = None

    # ──────────────────────────────────────────
    # INTERFACE PUBLIQUE
    # ──────────────────────────────────────────

    def set_on_new_data(self, callback):
        """Enregistre un callback appelé à chaque nouveau snapshot."""
        self._on_new_data = callback

    def set_valves(self, v1=None, v2=None, v3=None):
        """Modifie les vannes depuis l'API (commande opérateur)."""
        if v1 is not None:
            self._state["valve_v1"] = float(v1)
        if v2 is not None:
            self._state["valve_v2"] = float(v2)
        if v3 is not None:
            self._state["valve_v3"] = float(v3)

    def trigger_scenario(self, scenario_id: int):
        """Active un scénario de perturbation."""
        scenario = get_scenario(scenario_id)
        if scenario:
            self._active_scenario    = scenario
            self._scenario_start_time = time.time()
            self._oscillation_t       = 0.0
            
            # Ajouter à l'historique
            self._scenario_history.append({
                "id": scenario.id,
                "name": scenario.name,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            # Limiter l'historique aux 10 derniers
            if len(self._scenario_history) > 10:
                self._scenario_history.pop(0)

    def stop_scenario(self):
        """Arrête immédiatement le scénario en cours."""
        self._active_scenario = None
        self._scenario_start_time = None
        self._power_factor_offset = 0.0

    def reset(self):
        """Réinitialise l'état nominal complet."""
        self._state = {
            "pressure_hp":    NOMINAL["pressure_hp"],
            "temperature_hp": NOMINAL["temperature_hp"],
            "steam_flow_hp":  NOMINAL["steam_flow_hp"],
            "valve_v1":       NOMINAL["valve_v1"],
            "valve_v2":       NOMINAL["valve_v2"],
            "valve_v3":       NOMINAL["valve_v3"],
        }
        self._active_scenario      = None
        self._scenario_start_time  = None
        self._power_factor_offset  = 0.0
        self._oscillation_t        = 0.0

    def get_current(self) -> GTAParameters | None:
        return self._last_params

    # ──────────────────────────────────────────
    # BOUCLE ASYNCHRONE
    # ──────────────────────────────────────────

    async def run(self):
        """Boucle principale : génère un snapshot toutes les 500ms."""
        self._running = True
        interval = FAKE_API_INTERVAL_MS / 1000.0
        while self._running:
            nominal, simulated = self._generate_dual()
            self._last_params = simulated  # Par défaut, get_current renvoie la simu
            if self._on_new_data:
                await self._on_new_data(nominal, simulated)
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    # ──────────────────────────────────────────
    # GÉNÉRATION D'UN SNAPSHOT DUAL
    # ──────────────────────────────────────────

    def _generate_dual(self) -> tuple[GTAParameters, GTAParameters]:
        """Calcule l'état nominal (stable) et l'état simulé (avec pannes)."""
        
        # 1) État NOMINAL (Physique pure, sans scénarios, avec bruit minimal)
        state_nom = {
            "pressure_hp":    NOMINAL["pressure_hp"],
            "temperature_hp": NOMINAL["temperature_hp"],
            "steam_flow_hp":  NOMINAL["steam_flow_hp"],
            "valve_v1":       NOMINAL["valve_v1"],
            "valve_v2":       NOMINAL["valve_v2"],
            "valve_v3":       NOMINAL["valve_v3"],
        }
        # On n'ajoute pas de bruit sur les vannes si elles sont à 100% nominal
        # pour éviter le biais vers le bas (car 100% est le maximum physique).
        state_nom_noisy = self._add_noise(state_nom)
        for v in ["valve_v1", "valve_v2", "valve_v3"]:
            if state_nom[v] >= 100.0:
                state_nom_noisy[v] = 100.0
        
        computed_nom = self.physics.compute_all(**state_nom_noisy)
        params_nom = GTAParameters(
            timestamp = datetime.utcnow(),
            scenario  = None,
            status    = StatusEnum.NORMAL,
            **computed_nom
        )

        # 2) État SIMULÉ (Vannes manuelles + Scénarios + Bruit)
        state_sim = self._state.copy()
        scenario_name = None
        if self._active_scenario is not None:
            state_sim, scenario_name = self._apply_scenario(state_sim)
        state_sim = self._add_noise(state_sim)

        computed_sim = self.physics.compute_all(
            pressure_hp    = state_sim["pressure_hp"],
            temperature_hp = state_sim["temperature_hp"],
            steam_flow_hp  = state_sim["steam_flow_hp"],
            valve_v1       = state_sim["valve_v1"],
            valve_v2       = state_sim["valve_v2"],
            valve_v3       = state_sim["valve_v3"],
        )
        if self._power_factor_offset != 0:
            computed_sim["power_factor"] = round(
                max(0.70, computed_sim["power_factor"] + self._power_factor_offset), 3
            )
        status_sim = self._compute_status(computed_sim)
        
        params_sim = GTAParameters(
            timestamp = datetime.utcnow(),
            scenario  = scenario_name,
            status    = status_sim,
            **computed_sim
        )

        return params_nom, params_sim

    def _apply_scenario(self, state: dict) -> tuple[dict, str]:
        """Applique les deltas du scénario selon son type (ramp/step/oscillation)."""
        scenario   = self._active_scenario
        elapsed    = time.time() - self._scenario_start_time
        progress   = min(elapsed / scenario.duration_s, 1.0)
        deltas     = scenario.target_deltas

        if progress >= 1.0:
            # Scénario terminé : retour progressif au nominal
            self._active_scenario = None
            return state, None

        if scenario.perturbation_type == "step":
            factor = 1.0  # application immédiate

        elif scenario.perturbation_type == "ramp":
            factor = progress  # montée progressive

        elif scenario.perturbation_type == "oscillation":
            self._oscillation_t += FAKE_API_INTERVAL_MS / 1000.0
            factor = math.sin(2 * math.pi * self._oscillation_t / 10.0)  # période 10s

        else:
            factor = progress

        # Appliquer les deltas aux paramètres primaires
        for param, delta in deltas.items():
            if param == "power_factor_offset":
                self._power_factor_offset = delta * (1.0 if scenario.perturbation_type != "ramp" else progress)
            elif param in state:
                state[param] = state[param] + delta * factor

        # Contraintes physiques minimales
        state["pressure_hp"]    = max(0.0, state["pressure_hp"])
        state["temperature_hp"] = max(0.0, state["temperature_hp"])
        state["steam_flow_hp"]  = max(0.0, state["steam_flow_hp"])
        state["valve_v1"]       = max(0.0, min(100.0, state["valve_v1"]))
        state["valve_v2"]       = max(0.0, min(100.0, state["valve_v2"]))
        state["valve_v3"]       = max(0.0, min(100.0, state["valve_v3"]))

        return state, scenario.name

    def _add_noise(self, state: dict) -> dict:
        """Ajoute un bruit gaussien réaliste (±NOISE_LEVEL) à chaque paramètre."""
        noisy = {}
        for key, value in state.items():
            sigma      = abs(value) * NOISE_LEVEL
            v_noisy    = value + random.gauss(0, sigma)
            # Contrainte de plage pour les vannes après ajout de bruit
            if key in {"valve_v1", "valve_v2", "valve_v3"}:
                v_noisy = max(0.0, min(100.0, v_noisy))
            noisy[key] = v_noisy
        return noisy

    def _compute_status(self, params: dict) -> StatusEnum:
        """Détermine le statut global (NORMAL / DEGRADED / CRITICAL)."""
        from core.config import THRESHOLDS
        critical_count = 0
        warning_count  = 0
        # Marges relatives autour des seuils :
        # - ±3 % : toujours considéré comme NORMAL (tolérance au bruit)
        # - entre ±3 % et ±10 % : DEGRADED
        # - au-delà de ±10 % : CRITICAL
        warning_margin  = 0.03
        critical_margin = 0.10

        for param, limits in THRESHOLDS.items():
            value = params.get(param)
            if value is None:
                continue

            min_val = limits["min"]
            max_val = limits["max"]

            # Si on sort de la plage [min, max], c'est au moins DEGRADED
            if value < min_val or value > max_val:
                # Si on dépasse de plus de 5% de la plage, c'est CRITICAL
                range_span = max_val - min_val
                crit_margin = range_span * 0.25 if range_span > 0 else abs(min_val) * 0.1
                
                if value < (min_val - crit_margin) or value > (max_val + crit_margin):
                    critical_count += 1
                else:
                    warning_count += 1

        if critical_count >= 1:
            return StatusEnum.CRITICAL
        if warning_count >= 1:
            return StatusEnum.DEGRADED
        return StatusEnum.NORMAL


# Instance globale partagée avec FastAPI
fake_api = FakeAPI()