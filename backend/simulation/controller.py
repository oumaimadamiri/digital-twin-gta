"""
simulation/controller.py — Superviseur Contrôle Commande GTA

Gère :
  - mode opérateur : MANUAL / AUTO
  - machine_state : STOPPED → ROLLING → SYNCHRONIZING → GRID_CONNECTED → TRIPPED
  - PID_POWER  (MW → V1 %)  active en GRID_CONNECTED
  - PID_SPEED  (RPM → V1 %) active en ROLLING (governor)
  - séquences : start_turbine (cascade 3 phases) / stop_turbine
  - arrêt d'urgence (Trip/AU)
  - audit log de toutes les commandes
"""

import time
import logging

from simulation.pid import PID
from simulation.valve_controller import valve_controller
from services.data_manager import data_manager
from core.config import (
    PID_POWER_KP, PID_POWER_KI, PID_POWER_KD,
    PID_POWER_OUT_MIN, PID_POWER_OUT_MAX,
    PID_SPEED_KP, PID_SPEED_KI, PID_SPEED_KD,
    PID_SPEED_OUT_MIN, PID_SPEED_OUT_MAX,
    SEQUENCE_START_DURATION_S, SEQUENCE_STOP_DURATION_S,
    SPEED_SYNC_THRESHOLD_RPM, SPEED_SYNC_HOLD_S,
    NOMINAL,
)

logger = logging.getLogger("gta.controller")

# ─────────────────────────────────────────────
# États machine (cycle de vie de la turbine)
# ─────────────────────────────────────────────
MACHINE_STATES = ("STOPPED", "ROLLING", "SYNCHRONIZING", "GRID_CONNECTED", "TRIPPED")


class Controller:
    """Superviseur Contrôle Commande — singleton, appelé depuis fake_api._generate_dual()."""

    def __init__(self):
        self.mode        = "MANUAL"
        self.tripped     = False
        self.machine_state = "GRID_CONNECTED"   # défaut : machine en exploitation

        # Consignes
        self._setpoint_power_mw:        float | None = None
        self._setpoint_speed_rpm:       float | None = None
        self._setpoint_pressure_hp_bar: float | None = None

        # PID puissance → V1 (actif en GRID_CONNECTED)
        self._pid = PID(
            kp=PID_POWER_KP, ki=PID_POWER_KI, kd=PID_POWER_KD,
            out_min=PID_POWER_OUT_MIN, out_max=PID_POWER_OUT_MAX,
        )
        # PID vitesse → V1 (actif en ROLLING — governor)
        self._pid_speed = PID(
            kp=PID_SPEED_KP, ki=PID_SPEED_KI, kd=PID_SPEED_KD,
            out_min=PID_SPEED_OUT_MIN, out_max=PID_SPEED_OUT_MAX,
        )

        self._last_pid_output: float | None = None
        self._last_pid_error:  float | None = None

        # Séquences
        self._sequence_state:    str         = "IDLE"
        self._sequence_name:     str | None  = None
        self._sequence_t0:       float | None = None
        self._sequence_duration: float       = 0.0
        self._sequence_start_mw: float       = 0.0
        self._sequence_end_mw:   float       = 0.0
        self._sequence_just_completed: bool  = False

        # Cache de la dernière mesure (pour la transition MANUAL→AUTO)
        self._last_power_mw_cache: float = 0.0
        self._last_speed_rpm_cache: float = NOMINAL["turbine_speed"]

        # Chrono pour la phase SYNCHRONIZING
        self._sync_entry_time: float | None = None

    # ──────────────────────────────────────────────────────
    # COMMANDES MODE / SETPOINTS / GAINS
    # ──────────────────────────────────────────────────────

    def set_mode(self, mode: str, operator: str = "Opérateur") -> dict:
        if mode == "AUTO" and self.tripped:
            return {"accepted": False, "message": "Trip actif — effectuez un Reset Trip avant de passer en AUTO."}

        before = self.mode
        if mode == self.mode:
            return {"accepted": True, "message": f"Déjà en mode {mode}."}

        if mode == "AUTO":
            current_v1 = valve_controller._valves["v1"].target
            if self.machine_state == "GRID_CONNECTED":
                # Seed PID puissance pour bumpless transfer
                error_0 = (self._setpoint_power_mw - self._last_power_mw_cache
                           if self._setpoint_power_mw else 0.0)
                seed = (current_v1 - self._pid.kp * error_0) / self._pid.ki if self._pid.ki > 0 else current_v1
                self._pid.seed(seed)
            elif self.machine_state == "ROLLING":
                # Seed PID vitesse
                sp_rpm = self._setpoint_speed_rpm or NOMINAL["turbine_speed"]
                error_0 = sp_rpm - self._last_speed_rpm_cache
                seed = (current_v1 - self._pid_speed.kp * error_0) / self._pid_speed.ki if self._pid_speed.ki > 0 else current_v1
                self._pid_speed.seed(seed)
        else:
            self._pid.reset()
            self._pid_speed.reset()
            if self._sequence_state in ("STARTING", "STOPPING"):
                progress = self.get_sequence_progress() or 0.0
                data_manager.log_operator_action(
                    user=operator, action_type="SEQUENCE_CANCEL",
                    target=self._sequence_name,
                    value_before=f"progress={round(progress, 3)}",
                    value_after="MANUAL_OVERRIDE",
                )
                self._sequence_state = "IDLE"
                self._sequence_t0    = None
                logger.info("[Controller] Séquence annulée par bascule MANUAL")

        self.mode = mode
        data_manager.log_operator_action(
            user=operator, action_type="MODE_CHANGE",
            target="mode", value_before=before, value_after=mode,
        )
        logger.info(f"[Controller] Mode → {mode}")
        return {"accepted": True, "message": f"Mode changé : {before} → {mode}"}

    def set_setpoint(
        self,
        power_mw:        float | None = None,
        speed_rpm:       float | None = None,
        pressure_hp_bar: float | None = None,
        operator:        str = "Opérateur",
    ) -> dict:
        before = {
            "power_mw":        self._setpoint_power_mw,
            "speed_rpm":       self._setpoint_speed_rpm,
            "pressure_hp_bar": self._setpoint_pressure_hp_bar,
        }
        if power_mw        is not None: self._setpoint_power_mw        = float(power_mw)
        if speed_rpm       is not None: self._setpoint_speed_rpm       = float(speed_rpm)
        if pressure_hp_bar is not None: self._setpoint_pressure_hp_bar = float(pressure_hp_bar)

        after = {
            "power_mw":        self._setpoint_power_mw,
            "speed_rpm":       self._setpoint_speed_rpm,
            "pressure_hp_bar": self._setpoint_pressure_hp_bar,
        }
        import json
        data_manager.log_operator_action(
            user=operator, action_type="SETPOINT_CHANGE",
            target="setpoints",
            value_before=json.dumps(before),
            value_after=json.dumps(after),
        )
        return {"accepted": True, "setpoints": after}

    def set_pid_gains(self, kp: float, ki: float, kd: float, operator: str = "Opérateur") -> dict:
        import json
        before = json.dumps({"kp": self._pid.kp, "ki": self._pid.ki, "kd": self._pid.kd})
        self._pid.kp = kp
        self._pid.ki = ki
        self._pid.kd = kd
        self._pid.reset()
        after = json.dumps({"kp": kp, "ki": ki, "kd": kd})
        data_manager.log_operator_action(
            user=operator, action_type="PID_TUNE",
            target="pid_gains", value_before=before, value_after=after,
        )
        return {"accepted": True, "kp": kp, "ki": ki, "kd": kd}

    # ──────────────────────────────────────────────────────
    # COMMANDES ARRÊT D'URGENCE
    # ──────────────────────────────────────────────────────

    def emergency_trip(self, operator: str = "Opérateur") -> dict:
        if self.tripped:
            return {"accepted": False, "message": "Trip déjà actif — aucune action requise."}
        before_mode = self.mode
        self.mode          = "MANUAL"
        self.tripped       = True
        self.machine_state = "TRIPPED"
        self._sequence_state = "TRIPPED"
        self._sequence_t0    = None
        self._pid.reset()
        self._pid_speed.reset()
        valve_controller.emergency_close()

        # Libérer le rotor du réseau → la vitesse décroît librement vers 0
        try:
            from simulation.dynamics import rotor_dynamics
            rotor_dynamics.reset_to_stop()
        except ImportError:
            pass

        data_manager.log_operator_action(
            user=operator, action_type="EMERGENCY_TRIP",
            target="v1", value_before=f"mode={before_mode}", value_after="V1=0 TRIPPED",
        )
        logger.critical(f"[Controller] AU/TRIP déclenché par {operator}")
        return {"accepted": True, "message": "TRIP exécuté — V1 fermé instantanément."}

    def reset_trip(self, operator: str = "Opérateur") -> dict:
        if not self.tripped:
            return {"accepted": False, "message": "Aucun trip actif."}
        self.tripped         = False
        self.machine_state   = "STOPPED"
        self._sequence_state = "IDLE"
        self._pid.reset()
        self._pid_speed.reset()
        # Réarmer la couche de protections
        try:
            from simulation.protection import protection_system
            protection_system.reset()
        except ImportError:
            pass
        data_manager.log_operator_action(
            user=operator, action_type="TRIP_RESET",
            target="trip", value_before="TRIPPED", value_after="STOPPED",
        )
        logger.info(f"[Controller] Trip réinitialisé → machine STOPPED")
        return {"accepted": True, "message": "Trip réinitialisé — machine prête pour démarrage."}

    # ──────────────────────────────────────────────────────
    # COMMANDES RÉSEAU (couplage / découplage)
    # ──────────────────────────────────────────────────────

    def connect_to_grid(self, operator: str = "Opérateur") -> dict:
        """Couple la machine au réseau (SYNCHRONIZING → GRID_CONNECTED)."""
        if self.machine_state not in ("SYNCHRONIZING", "GRID_CONNECTED"):
            return {"accepted": False,
                    "message": f"Couplage impossible en état {self.machine_state}. Requis : SYNCHRONIZING."}
        self._enter_grid_connected(operator=operator)
        return {"accepted": True, "message": "Machine couplée au réseau — PID puissance actif."}

    def disconnect_from_grid(self, operator: str = "Opérateur") -> dict:
        """Découple la machine du réseau (GRID_CONNECTED → ROLLING)."""
        if self.machine_state != "GRID_CONNECTED":
            return {"accepted": False,
                    "message": f"Découplage impossible en état {self.machine_state}."}
        self.machine_state = "ROLLING"
        self._pid.reset()
        sp_rpm = self._setpoint_speed_rpm or NOMINAL["turbine_speed"]
        self._pid_speed.seed(valve_controller._valves["v1"].target / max(self._pid_speed.ki, 1e-6))
        try:
            from simulation.dynamics import rotor_dynamics
            rotor_dynamics.unlock_from_grid()
        except ImportError:
            pass
        data_manager.log_operator_action(
            user=operator, action_type="GRID_DISCONNECT",
            target="grid", value_before="GRID_CONNECTED", value_after="ROLLING",
        )
        logger.info("[Controller] Découplage réseau → ROLLING")
        return {"accepted": True, "message": "Machine découplée — governor vitesse actif."}

    # ──────────────────────────────────────────────────────
    # COMMANDES SÉQUENCES
    # ──────────────────────────────────────────────────────

    def start_sequence(self, name: str, operator: str = "Opérateur", current_power_mw: float = 0.0) -> dict:
        if self.tripped:
            return {"accepted": False, "message": "Trip actif — reset requis."}
        if self._sequence_state in ("STARTING", "STOPPING"):
            return {"accepted": False, "message": f"Séquence '{self._sequence_name}' déjà en cours."}

        if name == "start_turbine":
            if self.machine_state in ("STOPPED", "TRIPPED"):
                # Cascade complète : STOPPED → ROLLING → SYNCHRO → GRID_CONNECTED
                self._enter_rolling(operator=operator)
                self._sequence_state    = "STARTING"
                self._sequence_name     = name
                self._sequence_t0       = time.time()
                self._sequence_duration = SEQUENCE_START_DURATION_S
                self._sequence_start_mw = 0.0
                self._sequence_end_mw   = NOMINAL["active_power"]
            else:
                # Déjà en exploitation — simple rampe puissance
                self._sequence_state    = "STARTING"
                self._sequence_name     = name
                self._sequence_t0       = time.time()
                self._sequence_duration = SEQUENCE_START_DURATION_S
                self._sequence_start_mw = current_power_mw
                self._sequence_end_mw   = NOMINAL["active_power"]
                if self.mode != "AUTO":
                    self.set_mode("AUTO", operator=operator)

        elif name == "stop_turbine":
            self._sequence_state    = "STOPPING"
            self._sequence_name     = name
            self._sequence_t0       = time.time()
            self._sequence_duration = SEQUENCE_STOP_DURATION_S
            self._sequence_start_mw = current_power_mw
            self._sequence_end_mw   = 0.0
            if self.mode != "AUTO":
                self.set_mode("AUTO", operator=operator)

        else:
            return {"accepted": False, "message": f"Séquence inconnue : '{name}'"}

        data_manager.log_operator_action(
            user=operator, action_type="SEQUENCE_START", target=name,
            value_before=str(round(current_power_mw, 2)),
            value_after=str(self._sequence_end_mw),
        )
        logger.info(f"[Controller] Séquence '{name}' démarrée par {operator}")
        return {"accepted": True, "sequence": name, "duration_s": self._sequence_duration}

    def cancel_sequence(self, operator: str = "Opérateur") -> dict:
        if self._sequence_state not in ("STARTING", "STOPPING"):
            return {"accepted": False, "message": "Aucune séquence en cours."}
        name     = self._sequence_name
        progress = self.get_sequence_progress() or 0.0
        self._sequence_state = "IDLE"
        self._sequence_t0    = None
        self._sequence_name  = None
        data_manager.log_operator_action(
            user=operator, action_type="SEQUENCE_CANCEL", target=name,
            value_before=f"progress={round(progress, 3)}", value_after="CANCELLED",
        )
        return {"accepted": True, "message": f"Séquence '{name}' annulée."}

    # ──────────────────────────────────────────────────────
    # BOUCLE PRINCIPALE — appelée depuis fake_api._generate_dual()
    # ──────────────────────────────────────────────────────

    def update(self, dt: float, current_power_mw: float, current_speed_rpm: float = 0.0):
        """
        Mise à jour du superviseur.
        - En AUTO + GRID_CONNECTED : PID_POWER → V1
        - En AUTO + ROLLING        : PID_SPEED → V1  (governor)
        - En MANUAL ou TRIPPED     : ne touche pas aux vannes
        """
        self._last_power_mw_cache = current_power_mw
        self._last_speed_rpm_cache = current_speed_rpm

        if self.mode != "AUTO" or self.tripped:
            return

        # Vérifier les transitions d'état automatiques
        self._check_auto_transitions(current_speed_rpm, current_power_mw)

        if self.machine_state == "ROLLING":
            self._update_speed_pid(dt, current_speed_rpm)

        elif self.machine_state in ("GRID_CONNECTED", "SYNCHRONIZING"):
            self._update_power_pid(dt, current_power_mw)

    def _update_speed_pid(self, dt: float, current_speed_rpm: float):
        """PID vitesse (governor) actif pendant la phase ROLLING."""
        sp_rpm   = self._setpoint_speed_rpm or NOMINAL["turbine_speed"]
        v1_target = self._pid_speed.compute(sp_rpm, current_speed_rpm, dt)
        self._last_pid_output = round(v1_target, 2)
        self._last_pid_error  = round(self._pid_speed.error, 3)
        result = valve_controller.set_valve("v1", v1_target)
        if not result.get("accepted"):
            self._pid_speed._integral -= self._pid_speed.error * dt

    def _update_power_pid(self, dt: float, current_power_mw: float):
        """PID puissance actif pendant la phase GRID_CONNECTED."""
        effective_setpoint = self._compute_sequence_setpoint(current_power_mw)
        if effective_setpoint is None:
            return
        v1_target = self._pid.compute(effective_setpoint, current_power_mw, dt)
        self._last_pid_output = round(v1_target, 2)
        self._last_pid_error  = round(self._pid.error, 3)
        result = valve_controller.set_valve("v1", v1_target)
        if not result.get("accepted"):
            self._pid._integral -= self._pid.error * dt

    def _check_auto_transitions(self, current_speed_rpm: float, current_power_mw: float):
        """Transitions automatiques du MachineState pendant les séquences."""
        nominal_rpm = NOMINAL["turbine_speed"]

        if self.machine_state == "ROLLING":
            # Vitesse proche du nominal → passer en SYNCHRONIZING
            if abs(current_speed_rpm - nominal_rpm) < SPEED_SYNC_THRESHOLD_RPM:
                self._enter_synchronizing()

        elif self.machine_state == "SYNCHRONIZING":
            # Attente de quelques secondes stables puis couplage automatique
            if self._sync_entry_time and (time.time() - self._sync_entry_time) >= SPEED_SYNC_HOLD_S:
                self._enter_grid_connected()

        elif self.machine_state == "GRID_CONNECTED":
            # Fin de séquence stop → machine arrêtée
            if (self._sequence_state == "IDLE"
                    and self._sequence_name is None
                    and current_power_mw < 0.5
                    and valve_controller._valves["v1"].current < 2.0):
                self._enter_stopped()

    # ──────────────────────────────────────────────────────
    # TRANSITIONS D'ÉTAT (helpers internes)
    # ──────────────────────────────────────────────────────

    def _enter_rolling(self, operator: str = "SYSTÈME"):
        before = self.machine_state
        self.machine_state   = "ROLLING"
        self._sync_entry_time = None
        self._setpoint_speed_rpm = NOMINAL["turbine_speed"]
        self._pid_speed.reset()
        self._pid_speed.seed(0.0)
        self.mode = "AUTO"
        try:
            from simulation.dynamics import rotor_dynamics
            rotor_dynamics.unlock_from_grid()
        except ImportError:
            pass
        data_manager.log_operator_action(
            user=operator, action_type="STATE_TRANSITION",
            target="machine_state", value_before=before, value_after="ROLLING",
        )
        logger.info("[Controller] → ROLLING (governor vitesse actif)")

    def _enter_synchronizing(self):
        self.machine_state    = "SYNCHRONIZING"
        self._sync_entry_time = time.time()
        self._pid_speed.reset()
        # Figer V1 à sa position courante pendant la fenêtre de synchro
        data_manager.log_operator_action(
            user="SYSTÈME", action_type="STATE_TRANSITION",
            target="machine_state", value_before="ROLLING", value_after="SYNCHRONIZING",
        )
        logger.info("[Controller] → SYNCHRONIZING (vitesse nominale atteinte)")

    def _enter_grid_connected(self, operator: str = "SYSTÈME"):
        before = self.machine_state
        self.machine_state    = "GRID_CONNECTED"
        self._sync_entry_time = None
        # Seed le PID puissance sur la position V1 courante (bumpless)
        current_v1 = valve_controller._valves["v1"].target
        seed = current_v1 / self._pid.ki if self._pid.ki > 0 else current_v1
        self._pid.seed(seed)
        # Consigne puissance nominale si aucune fixée
        if self._setpoint_power_mw is None:
            self._setpoint_power_mw = NOMINAL["active_power"]
        try:
            from simulation.dynamics import rotor_dynamics
            rotor_dynamics.lock_to_grid()
        except ImportError:
            pass
        data_manager.log_operator_action(
            user=operator, action_type="STATE_TRANSITION",
            target="machine_state", value_before=before, value_after="GRID_CONNECTED",
        )
        logger.info("[Controller] → GRID_CONNECTED (PID puissance actif)")

    def _enter_stopped(self):
        before = self.machine_state
        self.machine_state = "STOPPED"
        self._pid.reset()
        self._pid_speed.reset()
        try:
            from simulation.dynamics import rotor_dynamics
            rotor_dynamics.unlock_from_grid()
        except ImportError:
            pass
        data_manager.log_operator_action(
            user="SYSTÈME", action_type="STATE_TRANSITION",
            target="machine_state", value_before=before, value_after="STOPPED",
        )
        logger.info("[Controller] → STOPPED (machine à l'arrêt)")

    # ──────────────────────────────────────────────────────
    # LOGIQUE SÉQUENCE PUISSANCE
    # ──────────────────────────────────────────────────────

    def _compute_sequence_setpoint(self, current_power_mw: float) -> float | None:
        """Consigne puissance interpolée (séquence) ou fixe."""
        if self._sequence_state in ("STARTING", "STOPPING") and self._sequence_t0 is not None:
            # Pendant ROLLING, la puissance n'est pas encore pilotée par PID_POWER
            if self.machine_state == "ROLLING":
                return None

            elapsed  = time.time() - self._sequence_t0
            progress = min(elapsed / self._sequence_duration, 1.0) if self._sequence_duration > 0 else 1.0
            sp       = self._sequence_start_mw + (self._sequence_end_mw - self._sequence_start_mw) * progress

            if progress >= 1.0:
                self._sequence_state = "IDLE"
                self._sequence_t0    = None
                sp = self._sequence_end_mw
                self._setpoint_power_mw = sp
                self._sequence_just_completed = True
                logger.info(f"[Controller] Séquence '{self._sequence_name}' terminée.")
                data_manager.log_operator_action(
                    user="SYSTÈME", action_type="SEQUENCE_COMPLETED",
                    target=self._sequence_name,
                    value_after=str(round(sp, 2)), source="AUTO",
                )
                self._sequence_name = None

            return round(sp, 2)

        return self._setpoint_power_mw

    def get_sequence_progress(self) -> float | None:
        if self._sequence_state in ("STARTING", "STOPPING") and self._sequence_t0 is not None:
            elapsed = time.time() - self._sequence_t0
            return round(min(elapsed / self._sequence_duration, 1.0), 3) if self._sequence_duration > 0 else 1.0
        return None

    def auto_trip_for_scenario(self, scenario_id: int, operator: str = "SYSTÈME"):
        if not self.tripped:
            self.emergency_trip(operator=operator)
            logger.warning(f"[Controller] Auto-trip déclenché par scénario #{scenario_id}")

    # ──────────────────────────────────────────────────────
    # SNAPSHOT pour WebSocket + /control/state
    # ──────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "control_mode":        self.mode,
            "machine_state":       self.machine_state,
            "setpoint_power_mw":   self._setpoint_power_mw,
            "setpoint_speed_rpm":  self._setpoint_speed_rpm,
            "pid_kp":              self._pid.kp,
            "pid_ki":              self._pid.ki,
            "pid_kd":              self._pid.kd,
            "pid_error":           self._last_pid_error  if self.mode == "AUTO" else None,
            "pid_output":          self._last_pid_output if self.mode == "AUTO" else None,
            "sequence_state":      self._sequence_state,
            "sequence_progress":   self.get_sequence_progress(),
            "tripped":             self.tripped,
            "interlock_warnings":  valve_controller.get_warnings(),
            # Gains PID vitesse (governor)
            "pid_speed_kp":        self._pid_speed.kp,
            "pid_speed_ki":        self._pid_speed.ki,
            "pid_speed_kd":        self._pid_speed.kd,
        }

    def get_state_dict(self) -> dict:
        """État complet pour GET /control/state."""
        from simulation.avr_controller import avr_controller
        return {
            **self.snapshot(),
            "setpoint_pressure_hp_bar": self._setpoint_pressure_hp_bar,
            "pid_integral":             round(self._pid._integral, 4),
            "valve_state":              valve_controller.get_state(),
            **avr_controller.snapshot(),
        }


controller = Controller()
