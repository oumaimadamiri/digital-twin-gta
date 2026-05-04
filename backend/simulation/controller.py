"""
simulation/controller.py — Superviseur de la couche Contrôle Commande GTA

Gère :
  - mode opérateur : MANUAL / AUTO
  - consignes (setpoints) : puissance cible en MW
  - régulation PID : puissance MW → position V1 (%)
  - séquences : start_turbine (0→24 MW) / stop_turbine (courant→0)
  - arrêt d'urgence (Trip/AU) : fermeture instantanée V1 + bascule MANUAL
"""

import time
import logging

from simulation.pid import PID
from simulation.valve_controller import valve_controller
from services.data_manager import data_manager
from core.config import (
    PID_POWER_KP, PID_POWER_KI, PID_POWER_KD,
    PID_POWER_OUT_MIN, PID_POWER_OUT_MAX,
    SEQUENCE_START_DURATION_S, SEQUENCE_STOP_DURATION_S,
    NOMINAL,
)

logger = logging.getLogger("gta.controller")


class Controller:
    """Superviseur Contrôle Commande — singleton, appelé depuis fake_api._generate_dual()."""

    def __init__(self):
        self.mode   = "MANUAL"
        self.tripped = False

        # Consignes
        self._setpoint_power_mw:       float | None = None
        self._setpoint_speed_rpm:      float | None = None
        self._setpoint_pressure_hp_bar: float | None = None

        # PID puissance → V1 target
        self._pid = PID(
            kp=PID_POWER_KP, ki=PID_POWER_KI, kd=PID_POWER_KD,
            out_min=PID_POWER_OUT_MIN, out_max=PID_POWER_OUT_MAX,
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

    # ──────────────────────────────────────────────────────
    # COMMANDES (appelées depuis les routes HTTP)
    # ──────────────────────────────────────────────────────

    def set_mode(self, mode: str, operator: str = "Opérateur") -> dict:
        if mode == "AUTO" and self.tripped:
            return {"accepted": False, "message": "Trip actif — effectuez un Reset Trip avant de passer en AUTO."}

        before = self.mode
        if mode == self.mode:
            return {"accepted": True, "message": f"Déjà en mode {mode}."}

        if mode == "AUTO":
            # Transfert sans à-coup : seed l'intégrale pour que la première sortie PID
            # corresponde à la position V1 actuelle → pas de saut de commande
            current_v1 = valve_controller._valves["v1"].target
            if self._setpoint_power_mw is not None and self._setpoint_power_mw > 0:
                # intégrale = (target_V1 - Kp*erreur) / Ki  (Ki != 0)
                current_power = self._last_power_mw_cache
                error_0 = self._setpoint_power_mw - current_power if current_power else 0.0
                seed = (current_v1 - self._pid.kp * error_0) / self._pid.ki if self._pid.ki > 0 else 0.0
            else:
                seed = current_v1 / self._pid.ki if self._pid.ki > 0 else 0.0
            self._pid.seed(seed)
        else:
            # MANUAL : gel du PID
            self._pid.reset()
            if self._sequence_state in ("STARTING", "STOPPING"):
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
        power_mw: float | None = None,
        speed_rpm: float | None = None,
        pressure_hp_bar: float | None = None,
        operator: str = "Opérateur",
    ) -> dict:
        before = {
            "power_mw":        self._setpoint_power_mw,
            "speed_rpm":       self._setpoint_speed_rpm,
            "pressure_hp_bar": self._setpoint_pressure_hp_bar,
        }
        if power_mw is not None:
            self._setpoint_power_mw = float(power_mw)
        if speed_rpm is not None:
            self._setpoint_speed_rpm = float(speed_rpm)
        if pressure_hp_bar is not None:
            self._setpoint_pressure_hp_bar = float(pressure_hp_bar)

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
        logger.info(f"[Controller] Consigne puissance → {self._setpoint_power_mw} MW")
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

    def emergency_trip(self, operator: str = "Opérateur") -> dict:
        before_mode = self.mode
        # Passer MANUAL avant d'agir sur les vannes
        self.mode   = "MANUAL"
        self.tripped = True
        self._sequence_state = "TRIPPED"
        self._sequence_t0    = None
        self._pid.reset()
        valve_controller.emergency_close()
        data_manager.log_operator_action(
            user=operator, action_type="EMERGENCY_TRIP",
            target="v1",
            value_before=f"mode={before_mode}",
            value_after="V1=0 TRIPPED",
        )
        logger.critical(f"[Controller] AU/TRIP déclenché par {operator}")
        return {"accepted": True, "message": "TRIP exécuté — V1 fermé instantanément. Passez en inspection avant Reset."}

    def reset_trip(self, operator: str = "Opérateur") -> dict:
        if not self.tripped:
            return {"accepted": False, "message": "Aucun trip actif."}
        self.tripped = False
        self._sequence_state = "IDLE"
        self._pid.reset()
        data_manager.log_operator_action(
            user=operator, action_type="TRIP_RESET",
            target="trip", value_before="TRIPPED", value_after="IDLE",
        )
        logger.info(f"[Controller] Trip réinitialisé par {operator}")
        return {"accepted": True, "message": "Trip réinitialisé — machine prête."}

    def start_sequence(self, name: str, operator: str = "Opérateur", current_power_mw: float = 0.0) -> dict:
        if self.tripped:
            return {"accepted": False, "message": "Trip actif — reset requis."}
        if self._sequence_state in ("STARTING", "STOPPING"):
            return {"accepted": False, "message": f"Séquence '{self._sequence_name}' déjà en cours."}

        if name == "start_turbine":
            self._sequence_state    = "STARTING"
            self._sequence_start_mw = current_power_mw          # depuis niveau actuel
            self._sequence_end_mw   = NOMINAL["active_power"]   # → 24 MW
            self._sequence_duration = SEQUENCE_START_DURATION_S
        elif name == "stop_turbine":
            self._sequence_state    = "STOPPING"
            self._sequence_start_mw = current_power_mw
            self._sequence_end_mw   = 0.0
            self._sequence_duration = SEQUENCE_STOP_DURATION_S
        else:
            return {"accepted": False, "message": f"Séquence inconnue : '{name}'"}

        self._sequence_name = name
        self._sequence_t0   = time.time()

        # Force AUTO pour que le PID pilote la rampe
        if self.mode != "AUTO":
            self.set_mode("AUTO", operator=operator)

        data_manager.log_operator_action(
            user=operator, action_type="SEQUENCE_START",
            target=name,
            value_before=str(round(current_power_mw, 2)),
            value_after=str(self._sequence_end_mw),
        )
        logger.info(f"[Controller] Séquence '{name}' démarrée par {operator}")
        return {"accepted": True, "sequence": name, "duration_s": self._sequence_duration}

    def cancel_sequence(self, operator: str = "Opérateur") -> dict:
        if self._sequence_state not in ("STARTING", "STOPPING"):
            return {"accepted": False, "message": "Aucune séquence en cours."}
        name = self._sequence_name
        self._sequence_state = "IDLE"
        self._sequence_t0    = None
        self._sequence_name  = None
        data_manager.log_operator_action(
            user=operator, action_type="SEQUENCE_CANCEL", target=name,
        )
        return {"accepted": True, "message": f"Séquence '{name}' annulée."}

    # ──────────────────────────────────────────────────────
    # BOUCLE : appelée depuis fake_api._generate_dual()
    # ──────────────────────────────────────────────────────

    _last_power_mw_cache: float = 0.0

    def update(self, dt: float, current_power_mw: float):
        """
        Appelée avant valve_controller.update(dt) dans _generate_dual().
        En AUTO : calcule la sortie PID et l'envoie à valve_controller.set_valve("v1").
        En MANUAL : ne touche pas aux vannes.
        """
        self._last_power_mw_cache = current_power_mw

        if self.mode != "AUTO" or self.tripped:
            return

        # Calcul de la consigne de puissance (séquence ou fixe)
        effective_setpoint = self._compute_sequence_setpoint(current_power_mw)
        if effective_setpoint is None:
            return

        # PID puissance → cible V1
        v1_target = self._pid.compute(effective_setpoint, current_power_mw, dt)
        self._last_pid_output = round(v1_target, 2)
        self._last_pid_error  = round(self._pid.error, 3)

        # Commande vanne — les interlocks de valve_controller s'appliquent
        result = valve_controller.set_valve("v1", v1_target)
        if not result.get("accepted"):
            # Interlock déclenché : annuler l'intégration de ce tick (anti-windup actionneur)
            self._pid._integral -= self._pid.error * dt

    def _compute_sequence_setpoint(self, current_power_mw: float) -> float | None:
        """Retourne la consigne instantanée selon séquence ou setpoint fixe."""
        if self._sequence_state in ("STARTING", "STOPPING") and self._sequence_t0 is not None:
            elapsed  = time.time() - self._sequence_t0
            progress = min(elapsed / self._sequence_duration, 1.0) if self._sequence_duration > 0 else 1.0

            # Interpolation linéaire
            sp = self._sequence_start_mw + (self._sequence_end_mw - self._sequence_start_mw) * progress

            if progress >= 1.0:
                # Séquence terminée
                self._sequence_state = "IDLE"
                self._sequence_t0    = None
                sp = self._sequence_end_mw
                self._setpoint_power_mw = sp
                self._sequence_just_completed = True
                logger.info(f"[Controller] Séquence '{self._sequence_name}' terminée.")
                data_manager.log_operator_action(
                    user="SYSTÈME", action_type="SEQUENCE_COMPLETED",
                    target=self._sequence_name,
                    value_after=str(round(sp, 2)),
                    source="AUTO",
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
        """Déclenche un trip automatique pour les scénarios critiques (ex. perte pompe lube)."""
        if not self.tripped:
            self.emergency_trip(operator=operator)
            logger.warning(f"[Controller] Auto-trip déclenché par scénario #{scenario_id}")

    # ──────────────────────────────────────────────────────
    # SNAPSHOT pour le WebSocket (fusionné dans params_sim)
    # ──────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "control_mode":        self.mode,
            "setpoint_power_mw":   self._setpoint_power_mw,
            "pid_kp":              self._pid.kp,
            "pid_ki":              self._pid.ki,
            "pid_kd":              self._pid.kd,
            "pid_error":           self._last_pid_error,
            "pid_output":          self._last_pid_output,
            "sequence_state":      self._sequence_state,
            "sequence_progress":   self.get_sequence_progress(),
            "tripped":             self.tripped,
            "interlock_warnings":  valve_controller.get_warnings(),
        }

    def get_state_dict(self) -> dict:
        """État complet pour GET /control/state."""
        return {
            **self.snapshot(),
            "setpoint_speed_rpm":       self._setpoint_speed_rpm,
            "setpoint_pressure_hp_bar": self._setpoint_pressure_hp_bar,
            "valve_state":              valve_controller.get_state(),
        }


# Singleton global
controller = Controller()
