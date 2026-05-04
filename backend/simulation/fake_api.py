import asyncio
import math
import random
import time
import logging
from datetime import datetime, timedelta

from core.config import (
    NOMINAL, NOISE_LEVEL, FAKE_API_INTERVAL_MS,
    WARNING_MARGIN, CRITICAL_MARGIN, OSCILLATION_PERIOD_S, PF_MIN_CLAMP,
    TIMEZONE_OFFSET
)
from models.gta_parameters import GTAParameters, StatusEnum
from simulation.physics_model import PhysicsModel
from simulation.scenarios import get_scenario, Scenario
from simulation.valve_controller import valve_controller as _valve_controller
from simulation.controller import controller as _controller


logger = logging.getLogger("gta.simulation")

class FakeAPI:
    """
    Générateur de données simulées pour le GTA.
    Maintient l'état courant et applique les perturbations de scénario.
    """

    def __init__(self):
        self.physics = PhysicsModel()
        self._running = False

        # Contrôleur d'actionneurs (rampe, sécurité, butées)
        self._vc = _valve_controller
        # Sync positions initiales du contrôleur avec les valeurs nominales
        for _key, _nom in [("v1","valve_v1"),("v2","valve_v2"),("v3","valve_v3"),("bp","valve_bp")]:
            self._vc._valves[_key].current = NOMINAL.get(_nom, self._vc._valves[_key].config.default)
            self._vc._valves[_key].target  = NOMINAL.get(_nom, self._vc._valves[_key].config.default)

        # État courant des paramètres primaires non-vanne (modifiables)
        self._state = {
            "pressure_hp":    NOMINAL["pressure_hp"],
            "temperature_hp": NOMINAL["temperature_hp"],
            "steam_flow_hp":  NOMINAL["steam_flow_hp"],
            # Les positions vannes sont gérées par self._vc ; conservées ici
            # uniquement comme base pour les deltas de scénarios.
            "valve_v1":       NOMINAL["valve_v1"],
            "valve_v2":       NOMINAL["valve_v2"],
            "valve_v3":       NOMINAL["valve_v3"],
            "valve_bp":       NOMINAL["valve_bp"],
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

    def set_valves(self, v1=None, v2=None, v3=None, v_bp=None) -> dict:
        """Délègue la commande vannes au contrôleur d'actionneurs (rampe + sécurité)."""
        return self._vc.set_all(v1=v1, v2=v2, v3=v3, valve_bp=v_bp)

    def get_valve_positions(self) -> dict:
        """Retourne l'état complet des vannes (position courante, cible, statut)."""
        return self._vc.get_state()

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
                "timestamp": (datetime.now() + timedelta(hours=TIMEZONE_OFFSET)).strftime("%H:%M:%S")
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
            "valve_bp":       NOMINAL["valve_bp"],
        }
        self._vc.reset_to_nominal()
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
        logger.info(f"Démarrage de la simulation FakeAPI (intervalle: {interval}s)")
        while self._running:
            try:
                nominal, simulated = self._generate_dual()
                self._last_params = simulated  # Par défaut, get_current renvoie la simu
                if self._on_new_data:
                    await self._on_new_data(nominal, simulated)
            except Exception as e:
                logger.error(f"Erreur dans la boucle FakeAPI: {e}", exc_info=True)
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    # ──────────────────────────────────────────
    # GÉNÉRATION D'UN SNAPSHOT DUAL
    # ──────────────────────────────────────────

    def _generate_dual(self) -> tuple[GTAParameters, GTAParameters]:
        """Calcule l'état nominal (stable) et l'état simulé (avec pannes)."""
        dt = FAKE_API_INTERVAL_MS / 1000.0

        # Superviseur Contrôle Commande : calcule la consigne V1 en AUTO avant le ramp
        last_power = self._last_params.active_power if self._last_params else 0.0
        _controller.update(dt, current_power_mw=last_power)

        # Avancer le contrôleur d'actionneurs (applique les rampes de positionnement)
        self._vc.update(dt)
        actual = self._vc.get_positions()  # positions réelles après rampe {v1,v2,v3,bp}
        
        # 1) État NOMINAL (Physique pure, sans scénarios, avec bruit minimal)
        state_nom = {
            "pressure_hp":    NOMINAL["pressure_hp"],
            "temperature_hp": NOMINAL["temperature_hp"],
            "steam_flow_hp":  NOMINAL["steam_flow_hp"],
            "valve_v1":       NOMINAL["valve_v1"],
            "valve_v2":       NOMINAL["valve_v2"],
            "valve_v3":       NOMINAL["valve_v3"],
            "valve_bp":       NOMINAL["valve_bp"],
        }
        # On n'ajoute pas de bruit sur les vannes si elles sont à 100% nominal
        # pour éviter le biais vers le bas (car 100% est le maximum physique).
        state_nom_noisy = self._add_noise(state_nom)
        for v in ["valve_v1", "valve_v2", "valve_v3"]:
            if state_nom[v] >= 100.0:
                state_nom_noisy[v] = 100.0
        
        try:
            computed_nom = self.physics.compute_all(**state_nom_noisy)
            # Ajout des targets vannes nominaux
            computed_nom["valve_v1_target"] = state_nom["valve_v1"]
            computed_nom["valve_v2_target"] = state_nom["valve_v2"]
            computed_nom["valve_v3_target"] = state_nom["valve_v3"]
            computed_nom["valve_bp_target"] = state_nom["valve_bp"]

            params_nom = GTAParameters(
                timestamp = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET),
                scenario  = None,
                status    = StatusEnum.NORMAL,
                **computed_nom
            )
        except Exception as e:
            logger.error(f"Erreur lors de la création de params_nom: {e}")
            raise

        # 2) État SIMULÉ (Vannes contrôlées avec rampe + Scénarios + Bruit)
        state_sim = self._state.copy()
        # Remplacer les positions de vannes par les positions réelles du contrôleur
        state_sim["valve_v1"] = actual["v1"]
        state_sim["valve_v2"] = actual["v2"]
        state_sim["valve_v3"] = actual["v3"]
        state_sim["valve_bp"] = actual["bp"]

        scenario_name = None
        if self._active_scenario is not None:
            state_sim, scenario_name = self._apply_scenario(state_sim)
        state_sim = self._add_noise(state_sim)

        try:
            computed_sim = self.physics.compute_all(
                pressure_hp    = state_sim["pressure_hp"],
                temperature_hp = state_sim["temperature_hp"],
                steam_flow_hp  = state_sim["steam_flow_hp"],
                valve_v1       = state_sim["valve_v1"],
                valve_v2       = state_sim["valve_v2"],
                valve_v3       = state_sim["valve_v3"],
                valve_bp       = state_sim["valve_bp"],
            )
            # Targets depuis le contrôleur (consignes opérateur)
            computed_sim["valve_v1_target"] = self._vc._valves["v1"].target
            computed_sim["valve_v2_target"] = self._vc._valves["v2"].target
            computed_sim["valve_v3_target"] = self._vc._valves["v3"].target
            computed_sim["valve_bp_target"] = self._vc._valves["bp"].target

            # Appliquer les deltas du scénario sur les champs auxiliaires (non-primaires)
            # _apply_scenario ne touche que les clés présentes dans _state (entrées primaires).
            # Ce bloc post-traite les champs calculés (huile, paliers) qui ne sont pas dans _state.
            if self._active_scenario is not None and self._scenario_start_time is not None:
                elapsed  = time.time() - self._scenario_start_time
                progress = min(elapsed / self._active_scenario.duration_s, 1.0)
                if self._active_scenario.perturbation_type == "step":
                    aux_factor = 1.0
                elif self._active_scenario.perturbation_type == "ramp":
                    aux_factor = progress
                else:
                    aux_factor = math.sin(2 * math.pi * self._oscillation_t / OSCILLATION_PERIOD_S)

                for param, delta in self._active_scenario.target_deltas.items():
                    if (param in computed_sim
                            and param not in self._state
                            and param != "power_factor_offset"):
                        try:
                            computed_sim[param] = round(float(computed_sim[param]) + delta * aux_factor, 3)
                        except (TypeError, ValueError):
                            pass

                # État pompe huile — override progressif pendant scénario 10
                if self._active_scenario.id == 10:
                    if progress > 0.7:
                        computed_sim["lube_oil_pump"] = "OFF"
                        _controller.auto_trip_for_scenario(10, operator="SYSTÈME")
                    elif progress > 0.3:
                        computed_sim["lube_oil_pump"] = "AUX"

            if self._power_factor_offset != 0:
                computed_sim["power_factor"] = round(
                    max(PF_MIN_CLAMP, computed_sim["power_factor"] + self._power_factor_offset), 3
                )
            status_sim = self._compute_status(computed_sim)
            
            # Fusionner l'état superviseur Contrôle Commande dans le snapshot simulé
            ctrl_snap = _controller.snapshot()
            computed_sim.update(ctrl_snap)

            params_sim = GTAParameters(
                timestamp = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET),
                scenario  = scenario_name,
                status    = status_sim,
                **computed_sim
            )
        except Exception as e:
            logger.error(f"Erreur lors de la création de params_sim: {e}")
            raise

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
            factor = math.sin(2 * math.pi * self._oscillation_t / OSCILLATION_PERIOD_S)

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
        from core.config import THRESHOLDS, CRITICAL_MARGIN
        critical_count = 0
        warning_count  = 0

        for param, limits in THRESHOLDS.items():
            value = params.get(param)
            if value is None:
                continue

            min_val = limits.get("min")
            max_val = limits.get("max")
            if min_val is None or max_val is None:
                continue

            # Si on sort de la plage [min, max], c'est au moins DEGRADED
            if value < min_val or value > max_val:
                # Si on dépasse de plus de la marge critique (10% par défaut), c'est CRITICAL
                range_span = max_val - min_val
                crit_margin_abs = range_span * CRITICAL_MARGIN if range_span > 0 else abs(min_val) * CRITICAL_MARGIN
                
                if value < (min_val - crit_margin_abs) or value > (max_val + crit_margin_abs):
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