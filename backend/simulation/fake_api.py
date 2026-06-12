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
from simulation.avr_controller import avr_controller as _avr
from simulation.dynamics import rotor_dynamics as _rotor
from simulation.protection import protection_system as _prot
from simulation.degradation import degradation as _degradation
from simulation.attemperator import attemperator as _attemp
from simulation.condenser import condenser as _cond
from core.config import DEGRADATION_ENABLED, ATTEMPERATOR_ENABLED, CONDENSER_ENABLED
from simulation.sim_machine import SimMachine

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
        # Vannes au défaut VALVE_CONFIGS (v1/v2/v3=100%, bp=80%, bp_admit=0%) — régime nominal

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
        self._last_nominal_power: float = NOMINAL["active_power"]
        # Puissance, vitesse et pression HP simulées du dernier tick — utilisées par les PIDs
        self._last_simulated_power:       float = NOMINAL["active_power"]
        self._last_simulated_speed:       float = NOMINAL["turbine_speed"]
        # Mesures NOMINALES du tick précédent — nourrissent le controller/AVR réels
        self._last_nominal_speed:  float = NOMINAL["turbine_speed"]
        self._last_nominal_params: GTAParameters | None = None
        # Machine simulée « fork » — None hors scénario
        self._sim: SimMachine | None = None
        # Bac à sable manuel (fork sans scénario prédéfini) — pour ESV/AVR/lubrification
        self._sandbox_manual: bool = False

        # Callback appelé à chaque nouveau snapshot
        self._on_new_data = None

    # ──────────────────────────────────────────
    # INTERFACE PUBLIQUE
    # ──────────────────────────────────────────

    def set_on_new_data(self, callback):
        """Enregistre un callback appelé à chaque nouveau snapshot."""
        self._on_new_data = callback

    def set_valves(self, v1=None, v2=None, v3=None, v_bp=None) -> dict:
        """Délègue la commande vannes au contrôleur actif : le fork simulé si un
        scénario est en cours, sinon la machine réelle (sim == réelle hors scénario)."""
        target = self._sim.valves if self._sim is not None else self._vc
        return target.set_all(v1=v1, v2=v2, v3=v3, valve_bp=v_bp)

    def get_valve_positions(self) -> dict:
        """Retourne l'état des vannes du contrôleur actif (fork simulé si scénario
        en cours, sinon machine réelle)."""
        target = self._sim.valves if self._sim is not None else self._vc
        return target.get_state()

    def set_esv(self, open_: bool, operator: str = "Opérateur") -> dict:
        """Ouvre/ferme l'ESV de la machine simulée — sandbox, scénario actif requis
        (comme AVR/lubrification). N'agit jamais sur la machine réelle."""
        if self._sim is None:
            return {"accepted": False, "message": "Aucun scénario actif — lancez un scénario pour piloter l'ESV simulée."}
        if open_:
            self._sim.valves.open_esv()
        else:
            self._sim.valves.close_esv()
        return {"accepted": True, "esv_open": self._sim.valves.esv_open}
    
    def set_lube_offsets(self, press_offset: float = 0.0, temp_offset: float = 0.0) -> dict:
        """Applique un offset manuel pression/température huile sur la machine simulée
        (sandbox, disponible uniquement pendant un scénario forké)."""
        if self._sim is None:
            return {"accepted": False, "message": "Aucun scénario actif — lancez un scénario pour utiliser le sandbox lubrification."}
        self._sim.lube_press_offset = press_offset
        self._sim.lube_temp_offset  = temp_offset
        return {"accepted": True, "lube_press_offset": press_offset, "lube_temp_offset": temp_offset}
    def set_avr_mode(self, mode: str, operator: str = "Opérateur") -> dict:
        """Mode AVR de la machine simulée (sandbox, disponible uniquement pendant un scénario forké)."""
        if self._sim is None:
            return {"accepted": False, "message": "Aucun scénario actif — lancez un scénario pour piloter l'excitation simulée."}
        return self._sim.avr.set_mode(mode, operator=operator)

    def set_avr_setpoint(self, voltage_kv: float | None = None, cosphi: float | None = None,
                          operator: str = "Opérateur") -> dict:
        """Consigne AVR de la machine simulée (sandbox, disponible uniquement pendant un scénario forké)."""
        if self._sim is None:
            return {"accepted": False, "message": "Aucun scénario actif — lancez un scénario pour piloter l'excitation simulée."}
        return self._sim.avr.set_setpoint(voltage_kv=voltage_kv, cosphi=cosphi, operator=operator)
    def set_avr_efd_manual(self, e_fd_pu: float, operator: str = "Opérateur") -> dict:
        """E_fd manuel AVR de la machine simulée (sandbox, disponible uniquement pendant un scénario forké)."""
        if self._sim is None:
            return {"accepted": False, "message": "Aucun scénario actif — lancez un scénario pour piloter l'excitation simulée."}
        return self._sim.avr.set_e_fd_manual(e_fd_pu, operator=operator)

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
        self._last_simulated_speed = 0.0
        self._sim = None
        self._sandbox_manual = False
        _rotor.reset_to_stop()

    def reset_sim_machine(self):
        """Reset machine simulée : efface un trip simulé, désactive le bac à sable
        et arrête le scénario → re-sync sur la réelle."""
        self._sim = None
        self._sandbox_manual = False
        self.stop_scenario()

    def toggle_sandbox(self, active: bool, operator: str = "Opérateur") -> dict:
        """Active/désactive le bac à sable manuel : crée/ferme le fork simulé sans
        scénario prédéfini, pour piloter ESV/AVR/lubrification/vannes sur une copie
        isolée de la machine sans perturber le flux nominal (IA/dashboard)."""
        self._sandbox_manual = active
        if not active and self._sim is not None and not self._sim.tripped and self._active_scenario is None:
            self._sim = None
        return {"accepted": True, "sandbox_active": self._sandbox_manual}

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
        """Calcule l'état nominal (machine réelle) et l'état simulé (fork sous scénario)."""
        dt = FAKE_API_INTERVAL_MS / 1000.0

        # Superviseur Contrôle-Commande nourri avec les mesures NOMINALES (machine réelle)
        # → les scénarios (flux simulé) ne perturbent plus la régulation réelle.
        _controller.update(
            dt,
            current_power_mw=self._last_nominal_power,
            current_speed_rpm=self._last_nominal_speed,
            current_freq_hz=_rotor.frequency_hz,
        )

        # AVR : intègre E_fd depuis les mesures NOMINALES du tick précédent
        _avr_v_default = 0.0 if _controller.machine_state in ("STOPPED", "TRIPPED") else NOMINAL.get("voltage", 10.5)
        _avr.update(
            dt,
            v_term_kv  =getattr(self._last_nominal_params, "voltage",        _avr_v_default),
            cosphi     =getattr(self._last_nominal_params, "power_factor",    NOMINAL.get("power_factor", 0.85)),
            i_stator_a =getattr(self._last_nominal_params, "current_a",       0.0),
            q_mvar     =getattr(self._last_nominal_params, "reactive_power",  0.0),
            s_max_mva  =NOMINAL.get("apparent_power_max", 41.0),
        )

        # Avancer le contrôleur d'actionneurs réel (rampes)
        self._vc.update(dt)
        actual = self._vc.get_positions()

        # ── 1) État NOMINAL (machine réelle) ───────────────────────────
        actual_nom = self._vc.get_positions()
        machine_st = _controller.machine_state

        if machine_st in ("STOPPED", "TRIPPED"):
            state_nom = {
                "pressure_hp":    NOMINAL["pressure_hp"],
                "temperature_hp": NOMINAL["temperature_hp"],
                "steam_flow_hp":  NOMINAL["steam_flow_hp"] if self._vc.esv_open else 0.0,
                "valve_v1":       actual_nom.get("v1", 0.0),
                "valve_v2":       actual_nom.get("v2", 0.0),
                "valve_v3":       actual_nom.get("v3", 0.0),
                "valve_bp":       actual_nom.get("bp",  NOMINAL["valve_bp"]),
                "valve_bp_admit": actual_nom.get("bp_admit", 0.0),
            }
        else:
            state_nom = {
                "pressure_hp":    NOMINAL["pressure_hp"],
                "temperature_hp": NOMINAL["temperature_hp"],
                "steam_flow_hp":  NOMINAL["steam_flow_hp"],
                "valve_v1":       actual_nom.get("v1", NOMINAL["valve_v1"]),
                "valve_v2":       actual_nom.get("v2", NOMINAL["valve_v2"]),
                "valve_v3":       actual_nom.get("v3", NOMINAL["valve_v3"]),
                "valve_bp":       actual_nom.get("bp",  NOMINAL["valve_bp"]),
            }

        state_nom_noisy = self._add_noise(state_nom)
        for v in ["valve_v1", "valve_v2", "valve_v3"]:
            if state_nom[v] >= 100.0:
                state_nom_noisy[v] = 100.0

        try:
            computed_nom = self.physics.compute_all(**state_nom_noisy, esv_open=self._vc.esv_open)
            computed_nom["esv_open"] = self._vc.esv_open
            computed_nom["valve_v1_target"] = self._vc._valves["v1"].target
            computed_nom["valve_v2_target"] = self._vc._valves["v2"].target
            computed_nom["valve_v3_target"] = self._vc._valves["v3"].target
            computed_nom["valve_bp_target"] = self._vc._valves["bp"].target
            computed_nom["valve_bp_admit"]        = actual_nom.get("bp_admit", 0.0)
            computed_nom["valve_bp_admit_target"] = self._vc._valves["bp_admit"].target

            # Rotor NOMINAL piloté par la vitesse algébrique NOM simulée)
            algebraic_speed_nom = computed_nom.get("turbine_speed", NOMINAL["turbine_speed"])
            _rotor.update(dt, target_speed_rpm=algebraic_speed_nom)
            computed_nom["turbine_speed"]    = _rotor.speed_rpm
            computed_nom["grid_frequency"]   = _rotor.frequency_hz
            computed_nom["alternator_speed"] = round(_rotor.speed_rpm / PhysicsModel.GEAR_RATIO, 1)

            nom_ctrl = _controller.snapshot()
            computed_nom["machine_state"]  = nom_ctrl.get("machine_state", "STOPPED")
            computed_nom["startup_phase"]  = nom_ctrl.get("startup_phase", "PRE_CHECKS")
            computed_nom["tripped"]        = nom_ctrl.get("tripped", False)
            computed_nom["control_mode"]   = nom_ctrl.get("control_mode", "MANUAL")
            computed_nom.update(_avr.snapshot())

            status_nom = self._compute_status(computed_nom)
            params_nom = GTAParameters(
                timestamp = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET),
                scenario  = None,
                status    = status_nom,
                **computed_nom
            )
        except Exception as e:
            logger.error(f"Erreur lors de la création de params_nom: {e}")
            raise

        # Réconciliation Trip ↔ Scénario sur la machine réelle
        if _controller.tripped and self._active_scenario is not None:
            self.stop_scenario()

        # ── 2) Cycle de vie du fork machine simulée ────────────────────
        if (self._active_scenario is not None or self._sandbox_manual) and self._sim is None:
            self._sim = SimMachine()
            self._sim.fork_from(_controller, self._vc, _rotor, _avr)
        elif (self._active_scenario is None and not self._sandbox_manual
              and self._sim is not None and not self._sim.tripped):
            self._sim = None  # re-sync sur la machine réelle

        forked = self._sim is not None
        if forked:
            # Supervision simulée : PID puissance + rampe vanneslé)
            self._sim.step(dt, self._last_simulated_power)

        # ── 3) État SIMULÉ ─────────────────────────────────────────────
        state_sim = self._state.copy()
        if forked:
            sim_pos = self._sim.valves.get_positions()
            sim_esv = self._sim.valves.esv_open
        else:
            sim_pos = actual
            sim_esv = self._vc.esv_open
        state_sim["valve_v1"]       = sim_pos["v1"]
        state_sim["valve_v2"]       = sim_pos["v2"]
        state_sim["valve_v3"]       = sim_pos["v3"]
        state_sim["valve_bp"]       = sim_pos["bp"]
        state_sim["valve_bp_admit"] = sim_pos.get("bp_admit", 0.0)

        scenario_name = None
        if self._active_scenario is not None:
            state_sim, scenario_name = self._apply_scenario(state_sim)
        state_sim = self._add_noise(state_sim)

        if ATTEMPERATOR_ENABLED:
            t_out, _inj = _attemp.step(state_sim["temperature_hp"], dt)
            state_sim["temperature_hp"] = t_out

        try:
            computed_sim = self.physics.compute_all(
                pressure_hp    = state_sim["pressure_hp"],
                temperature_hp = state_sim["temperature_hp"],
                steam_flow_hp  = state_sim["steam_flow_hp"],
                valve_v1       = state_sim["valve_v1"],
                valve_v2       = state_sim["valve_v2"],
                valve_v3       = state_sim["valve_v3"],
                valve_bp       = state_sim["valve_bp"],
                valve_bp_admit = state_sim.get("valve_bp_admit", 0.0),
                esv_open       = sim_esv,
            )
            computed_sim["esv_open"] = sim_esv
            computed_sim["sandbox_active"] = forked
            _vsrc = self._sim.valves if forked else self._vc
            computed_sim["valve_v1_target"]       = _vsrc._valves["v1"].target
            computed_sim["valve_v2_target"]       = _vsrc._valves["v2"].target
            computed_sim["valve_v3_target"]       = _vsrc._valves["v3"].target
            computed_sim["valve_bp_target"]       = _vsrc._valves["bp"].target
            computed_sim["valve_bp_admit"]        = state_sim.get("valve_bp_admit", 0.0)
            computed_sim["valve_bp_admit_target"] = _vsrc._valves["bp_admit"].target

            # Lubrification — offsets manuels (sandbox, fork uniquement)
            if forked and (self._sim.lube_press_offset or self._sim.lube_temp_offset):
                p_off = self._sim.lube_press_offset
                t_off = self._sim.lube_temp_offset
                computed_sim["lube_oil_press"]     = round(max(0.0, computed_sim["lube_oil_press"] + p_off), 2)
                computed_sim["lube_oil_temp"]      = round(max(0.0, computed_sim["lube_oil_temp"] + t_off), 1)
                computed_sim["lube_oil_temp_out"]  = round(max(0.0, computed_sim["lube_oil_temp_out"] + t_off), 1)
                # Conséquences mécaniques : huile chaude/basse pression → échauffement vibrations & paliers
                temp_penalty = max(0.0, -p_off) * 8.0 + max(0.0, t_off) * 0.5
                vib_penalty  = max(0.0, -p_off) * 1.5 + max(0.0, t_off)*0.5
                computed_sim["temp_bearing_fwd"] = round(computed_sim.get("temp_bearing_fwd", 74.0) + temp_penalty, 2)
                computed_sim["temp_bearing_aft"] = round(computed_sim.get("temp_bearing_aft", 76.0) + temp_penalty, 2)
                computed_sim["vib_bearing_fwd"]  = round(computed_sim.get("vib_bearing_fwd", 2.1) + vib_penalty, 3)
                computed_sim["vib_bearing_aft"]  = round(computed_sim.get("vib_bearing_aft", 1.8) + vib_penalty, 3)

            # Deltas scénario sur champs auxiliaires (huile, paliers…)
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

                # Scénario 10 — pompe huile → trip de la machine SIMULÉE uniquement
                if self._active_scenario.id == 10:
                    if progress > 0.7:
                        computed_sim["lube_oil_pump"] = "OFF"
                        if forked:
                            self._sim.emergency_trip(operator="SCENARIO:10")
                    elif progress > 0.3:
                        computed_sim["lube_oil_pump"] = "AUX"

            if self._power_factor_offset != 0:
                computed_sim["power_factor"] = round(
                    max(PF_MIN_CLAMP, computed_sim["power_factor"] + self._power_factor_offset), 3
                )

            # Rotor SIMULÉ : fork → rotor sim ; sinon → rotor nominal (identique au dashboard)
            algebraic_speed_sim = computed_sim.get("turbine_speed", NOMINAL["turbine_speed"])
            if forked:
                self._sim.rotor.update(dt, target_speed_rpm=algebraic_speed_sim)
                _rsrc = self._sim.rotor
            else:
                _rsrc = _rotor
            computed_sim["turbine_speed"]    = _rsrc.speed_rpm
            computed_sim["grid_frequency"]   = _rsrc.frequency_hz
            computed_sim["alternator_speed"] = round(_rsrc.speed_rpm / PhysicsModel.GEAR_RATIO, 1)

            if DEGRADATION_ENABLED:
                _drift = _degradation.update(dt, _controller.machine_state == "GRID_CONNECTED")
                computed_sim["efficiency"] = round(
                    max(0.0, computed_sim["efficiency"] + _drift["eff_drift_pct"]), 3
                )
                computed_sim["vib_bearing_fwd"] = round(
                    computed_sim.get("vib_bearing_fwd", 2.1) + _drift["vib_drift_mms"], 3
                )
                computed_sim["vib_bearing_aft"] = round(
                    computed_sim.get("vib_bearing_aft", 1.8) + _drift["vib_drift_mms"], 3
                )
                computed_sim["temp_bearing_fwd"] = round(
                    computed_sim.get("temp_bearing_fwd", 74.0) +_drift["bearing_temp_drift_c"], 2
                )
                computed_sim["temp_bearing_aft"] = round(
                    computed_sim.get("temp_bearing_aft", 76.0) + _drift["bearing_temp_drift_c"], 2
                )

            if ATTEMPERATOR_ENABLED:
                computed_sim.update(_attemp.snapshot())
            if CONDENSER_ENABLED:
                computed_sim.update(_cond.step(dt, computed_sim.get("steam_flow_condenser", 0.0)))

            # Fusion superviseur + AVR (état réel), puis override par le contexte SIM si forké
            computed_sim.update(_controller.snapshot())
            computed_sim.update(_avr.snapshot())
            if forked:
                computed_sim["machine_state"] = self._sim.machine_state
                computed_sim["tripped"]       = self._sim.tripped
                computed_sim["control_mode"]  = self._sim.mode
                if self._sim.tripped:
                    computed_sim["voltage"]        = 0.0
                    computed_sim["current_a"]      = 0.0
                    computed_sim["active_power"]   = 0.0
                    computed_sim["reactive_power"] = 0.0
                # AVR forké : excitation simulée indépendante de la machine réelle,
                # nourrie par les mesures SIM du tick précédent (self._last_params)
                self._sim.avr.update(
                    dt,
                    v_term_kv  = getattr(self._last_params, "voltage",       NOMINAL.get("voltage", 10.5)),
                    cosphi     = getattr(self._last_params, "power_factor",  NOMINAL.get("power_factor", 0.85)),
                    i_stator_a = getattr(self._last_params, "current_a",     0.0),
                    q_mvar     = getattr(self._last_params, "reactive_power", 0.0),
                    s_max_mva  = NOMINAL.get("apparent_power_max", 41.0),
                )
                computed_sim.update(self._sim.avr.snapshot())

            status_sim = self._compute_status(computed_sim)
            params_sim = GTAParameters(
                timestamp = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET),
                scenario  = scenario_name,
                status    = status_sim,
                **computed_sim
            )

            # Protections : sur la machine SIMULÉE si forké, sin
            if forked:
                self._sim.protection.check_all(params_sim, self._sim, _avr)
            else:
                _prot.check_all(params_sim, _controller, _avr)

        except Exception as e:
            logger.error(f"Erreur lors de la création de params_sim: {e}")
            raise

        self._last_nominal_power   = params_nom.active_power
        self._last_nominal_speed   = params_nom.turbine_speed
        self._last_nominal_params  = params_nom
        self._last_simulated_power = params_sim.active_power
        self._last_simulated_speed = params_sim.turbine_speed
        return params_nom, params_sim

    def _apply_scenario(self, state: dict) -> tuple[dict, str]:
        """Applique les deltas du scénario selon son type (ramp/step/oscillation)."""
        scenario   = self._active_scenario
        elapsed    = time.time() - self._scenario_start_time
        progress   = min(elapsed / scenario.duration_s, 1.0)
        deltas     = scenario.target_deltas

        if progress >= 1.0:
            # Scénario terminé : conserver le nom ce tick pour éviter race condition UI
            finished_name = scenario.name
            self._active_scenario = None
            self._scenario_start_time = None
            return state, finished_name

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
            if key in {"valve_v1", "valve_v2", "valve_v3", "valve_bp", "valve_bp_admit"}:
                v_noisy = max(0.0, min(100.0, v_noisy))
            noisy[key] = v_noisy
        return noisy

    def _compute_status(self, params: dict) -> StatusEnum:
        """Détermine le statut global (NORMAL / DEGRADED / CRITICAL)."""
        from core.config import THRESHOLDS, CRITICAL_MARGIN
        # Machine trippée → TRIPPED ; machine à l'arrêt normal → NORMAL
        machine_st = params.get("machine_state") or _controller.machine_state
        if machine_st == "TRIPPED" or _controller.tripped:
            return StatusEnum.TRIPPED
        if machine_st == "STOPPED":
            return StatusEnum.NORMAL

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