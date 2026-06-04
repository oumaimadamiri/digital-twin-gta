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

import math
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
    PID_PRESSURE_KP, PID_PRESSURE_KI, PID_PRESSURE_KD,
    PID_PRESSURE_OUT_MIN, PID_PRESSURE_OUT_MAX,
    PRESSURE_HP_SETPOINT_BAR,
    SEQUENCE_START_DURATION_S, SEQUENCE_STOP_DURATION_S,
    SPEED_SYNC_THRESHOLD_RPM, SPEED_SYNC_HOLD_S,
    DROOP_ENABLED, DROOP_R, DROOP_FREQ_REF_HZ, DROOP_DEADBAND_HZ, DROOP_MAX_DELTA_MW,
    ESV_MIN_SPEED_RPM, GRID_COUPLE_FREQ_TOL_HZ,
    AUTO_STEP_DELAY_BARRAGE_S, AUTO_STEP_DELAY_ESV_S, AUTO_STEP_DELAY_V1_S,
    AUTO_STEP_DELAY_EXCITE_S, AUTO_STEP_DELAY_SYNC_ARM_S,
    NOMINAL,
)

logger = logging.getLogger("gta.controller")

# ─────────────────────────────────────────────
# États machine (cycle de vie de la turbine)
# ─────────────────────────────────────────────
MACHINE_STATES  = ("STOPPED", "ROLLING", "SYNCHRONIZING", "GRID_CONNECTED", "TRIPPED")
STARTUP_PHASES  = (
    "PRE_CHECKS",      # posture post-AU, pré-checks OK
    "BARRAGE_OPENED",  # vapeur de barrage ouverte, rotor en rotation lente
    "ESV_OPENED",      # ESV ouverte, admission HP disponible
    "V1_OPENING",      # V1 en cours d'ouverture
    "ACCELERATING",    # V1 ouverte, rampe de vitesse vers nominale
    "READY_TO_EXCITE", # vitesse nominale atteinte, prêt à exciter l'alternateur
    "EXCITED",         # AVR actif, tension en montée
    "SYNCHRONIZING",   # en attente de couplage réseau
    "GRID_CONNECTED",  # machine couplée
)


class Controller:
    """Superviseur Contrôle Commande — singleton, appelé depuis fake_api._generate_dual()."""

    def __init__(self):
        self.mode        = "AUTO"
        self.tripped     = False
        self.machine_state = "GRID_CONNECTED"

        # Consignes
        self._setpoint_power_mw:        float | None = NOMINAL["active_power"]
        self._setpoint_speed_rpm:       float | None = NOMINAL["turbine_speed"]
        self._setpoint_pressure_hp_bar: float | None = NOMINAL["pressure_hp"]

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
        # PID pression HP → V1 (actif en GRID_CONNECTED si regulation_target == "PRESSURE")
        # Convention de signe : V1↑ → débit ↑ → pression header HP ↓ (boiler limité)
        # On inverse setpoint/measured dans compute() pour obtenir le sens correct.
        self._pid_pressure = PID(
            kp=PID_PRESSURE_KP, ki=PID_PRESSURE_KI, kd=PID_PRESSURE_KD,
            out_min=PID_PRESSURE_OUT_MIN, out_max=PID_PRESSURE_OUT_MAX,
        )
        # Cible de régulation : "POWER" (défaut) ou "PRESSURE"
        self._regulation_target: str = "POWER"
        # Cache pression HP pour le tick courant (évite couplage circulaire)
        self._last_pressure_hp_bar_cache: float = NOMINAL["pressure_hp"]

        # Pré-seed intégrateurs : machine déjà au point d'équilibre nominal au boot.
        # output = ki · integral à erreur nulle → integral = V1_nominal / ki
        # Sans ce seed, tick 1 calcule output=0 → V1.target=0 → oscillation 3 cycles.
        _v1_nom = NOMINAL["valve_v1"]  # 100.0
        if self._pid.ki > 0:
            self._pid.seed(_v1_nom / self._pid.ki)            # 100/0.5 = 200.0
        if self._pid_pressure.ki > 0:
            self._pid_pressure.seed(_v1_nom / self._pid_pressure.ki)  # 100/0.25 = 400.0

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
        self._last_power_mw_cache: float = NOMINAL["active_power"]
        self._last_speed_rpm_cache: float = NOMINAL["turbine_speed"]

        # Droop primaire — cache fréquence + dernier offset calculé
        self._last_freq_hz_cache: float = DROOP_FREQ_REF_HZ
        self._last_droop_offset_mw: float = 0.0

        # Chrono pour la phase SYNCHRONIZING
        self._sync_entry_time: float | None = None

        # Phase de démarrage manuel (orthogonale à machine_state)
        self.startup_phase:     str         = "GRID_CONNECTED"
        self._phase_entered_at: float       = time.time()
        self._phase_message:    str | None  = None

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
            self._pid_pressure.reset()
            self._regulation_target = "POWER"
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

        # Bascule AUTO depuis machine arrêtée (post-reset trip ou boot froid) :
        # déclencher la séquence de démarrage orchestrée pas-à-pas.
        # start_sequence("start_turbine") initialise _sequence_state="STARTING" et
        # _check_auto_transitions pilote la cascade barrage→ESV→V1→AVR→sync→couple.
        if mode == "AUTO" and self.machine_state == "STOPPED" and self._sequence_state == "IDLE":
            self.start_sequence("start_turbine", operator=operator)

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

    def set_regulation_target(self, target: str, operator: str = "Opérateur") -> dict:
        """Bascule entre régulation POWER (puissance → V1) et PRESSURE (pression HP → V1).
        Réservé à l'état GRID_CONNECTED uniquement."""
        if target not in ("POWER", "PRESSURE"):
            return {"accepted": False, "message": f"Cible invalide '{target}'. Valeurs : POWER, PRESSURE."}
        if target == "PRESSURE" and self.machine_state != "GRID_CONNECTED":
            return {"accepted": False,
                    "message": f"Régulation PRESSURE impossible en état {self.machine_state}. Requis : GRID_CONNECTED."}

        before = self._regulation_target
        if before == target:
            return {"accepted": True, "message": f"Déjà en régulation {target}."}

        current_v1 = valve_controller._valves["v1"].target

        if target == "PRESSURE":
            # Bumpless : seed _pid_pressure depuis position V1 courante
            seed = current_v1 / self._pid_pressure.ki if self._pid_pressure.ki > 0 else current_v1
            self._pid_pressure.seed(seed)
            self._pid.reset()
        else:  # POWER
            # Bumpless : seed _pid puissance depuis position V1 courante
            seed = current_v1 / self._pid.ki if self._pid.ki > 0 else current_v1
            self._pid.seed(seed)
            self._pid_pressure.reset()

        self._regulation_target = target
        data_manager.log_operator_action(
            user=operator, action_type="REGULATION_TARGET_CHANGE",
            target="regulation_target", value_before=before, value_after=target,
        )
        logger.info("[Controller] Régulation → %s (par %s)", target, operator)
        return {"accepted": True, "regulation_target": target, "bumpless_seed": round(current_v1, 2)}

    def set_pid_gains(self, kp: float, ki: float, kd: float,
                      operator: str = "Opérateur", loop: str = "power") -> dict:
        import json
        pid_map = {"power": self._pid, "speed": self._pid_speed, "pressure": self._pid_pressure}
        pid = pid_map.get(loop, self._pid)
        before = json.dumps({"kp": pid.kp, "ki": pid.ki, "kd": pid.kd})
        pid.kp = kp
        pid.ki = ki
        pid.kd = kd
        pid.reset()
        after = json.dumps({"kp": kp, "ki": ki, "kd": kd})
        data_manager.log_operator_action(
            user=operator, action_type="PID_TUNE",
            target=f"pid_{loop}_gains", value_before=before, value_after=after,
        )
        return {"accepted": True, "loop": loop, "kp": kp, "ki": ki, "kd": kd}

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
        self._pid_pressure.reset()
        self._regulation_target = "POWER"
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
        self._pid_pressure.reset()
        self._regulation_target = "POWER"
        # Réarmer la couche de protections
        try:
            from simulation.protection import protection_system
            protection_system.reset()
        except ImportError:
            pass
        # Remettre les vannes en posture de démarrage propre
        try:
            valve_controller.reset_after_trip()
        except Exception:
            pass
        # Couper l'excitation
        try:
            from simulation.avr_controller import avr_controller as _avr
            _avr.shutdown(operator=operator)
        except Exception:
            pass
        # Libérer le rotor du réseau
        try:
            from simulation.dynamics import rotor_dynamics
            rotor_dynamics.unlock_from_grid()
        except ImportError:
            pass
        # Remettre la phase de démarrage à zéro
        self._advance_phase("PRE_CHECKS")
        data_manager.log_operator_action(
            user=operator, action_type="TRIP_RESET",
            target="trip", value_before="TRIPPED", value_after="STOPPED",
        )
        logger.info(f"[Controller] Trip réinitialisé → machine STOPPED, phase PRE_CHECKS")
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
                # Séquence complète orchestrée pas-à-pas (AUTO) : STOPPED → ... → GRID_CONNECTED
                # _check_auto_transitions pilotera chaque étape (barrage→ESV→V1→AVR→sync→couple)
                # _sequence_t0 = None jusqu'au couplage réseau (la rampe MW commence après)
                self._sequence_state    = "STARTING"
                self._sequence_name     = name
                self._sequence_t0       = None
                self._sequence_duration = SEQUENCE_START_DURATION_S
                self._sequence_start_mw = 0.0
                self._sequence_end_mw   = NOMINAL["active_power"]
                if self.mode != "AUTO":
                    self.set_mode("AUTO", operator=operator)
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
        was_starting = (self._sequence_state == "STARTING")
        self._sequence_state = "IDLE"
        self._sequence_t0    = None
        self._sequence_name  = None
        # Si annulation d'un démarrage avant couplage réseau → retour STOPPED
        if was_starting and self.machine_state not in ("GRID_CONNECTED",):
            self.machine_state = "STOPPED"
            self._pid.reset()
            self._pid_speed.reset()
            self._pid_pressure.reset()
            try:
                valve_controller.emergency_close()
            except Exception:
                pass
        data_manager.log_operator_action(
            user=operator, action_type="SEQUENCE_CANCEL", target=name,
            value_before=f"progress={round(progress, 3)}", value_after="CANCELLED",
        )
        return {"accepted": True, "message": f"Séquence '{name}' annulée."}

    # ──────────────────────────────────────────────────────
    # BOUCLE PRINCIPALE — appelée depuis fake_api._generate_dual()
    # ──────────────────────────────────────────────────────

    def update(
        self,
        dt: float,
        current_power_mw: float,
        current_speed_rpm: float = 0.0,
        current_pressure_hp_bar: float | None = None,
        current_freq_hz: float | None = None,
    ):
        """
        Mise à jour du superviseur.
        - En AUTO + GRID_CONNECTED + POWER    : PID_POWER + droop → V1
        - En AUTO + GRID_CONNECTED + PRESSURE : PID_PRESSURE → V1
        - En AUTO + ROLLING                   : PID_SPEED → V1  (governor)
        - En MANUAL ou TRIPPED                : ne touche pas aux vannes
        """
        self._last_power_mw_cache    = current_power_mw
        self._last_speed_rpm_cache   = current_speed_rpm
        if current_pressure_hp_bar is not None:
            self._last_pressure_hp_bar_cache = current_pressure_hp_bar
        self._last_freq_hz_cache = current_freq_hz if current_freq_hz is not None else DROOP_FREQ_REF_HZ

        if self.tripped:
            return

        # Transitions passives de phase (MANUAL et AUTO) — V1_OPENING/ACCELERATING/READY_TO_EXCITE
        self._tick_manual_phase(dt, current_speed_rpm)

        if self.mode != "AUTO":
            return

        # Vérifier les transitions d'état automatiques (séquence AUTO + ROLLING→SYNCHRO→GRID)
        self._check_auto_transitions(current_speed_rpm, current_power_mw)

        if self.machine_state == "ROLLING":
            self._update_speed_pid(dt, current_speed_rpm)

        elif self.machine_state in ("GRID_CONNECTED", "SYNCHRONIZING"):
            if (self.machine_state == "GRID_CONNECTED"
                    and self._regulation_target == "PRESSURE"):
                self._update_pressure_pid(dt, self._last_pressure_hp_bar_cache)
            else:
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
        """PID puissance actif pendant la phase GRID_CONNECTED, avec droop primaire."""
        effective_setpoint = self._compute_sequence_setpoint(current_power_mw)
        if effective_setpoint is None:
            return
        droop_offset = self._compute_droop_offset(self._last_freq_hz_cache)
        self._last_droop_offset_mw = round(droop_offset, 3)
        effective_setpoint = max(0.0, effective_setpoint + droop_offset)
        v1_target = self._pid.compute(effective_setpoint, current_power_mw, dt)
        self._last_pid_output = round(v1_target, 2)
        self._last_pid_error  = round(self._pid.error, 3)
        result = valve_controller.set_valve("v1", v1_target)
        if not result.get("accepted"):
            self._pid._integral -= self._pid.error * dt

    def _compute_droop_offset(self, freq_hz: float) -> float:
        """Droop primaire 4 % : ΔP = -(P_nom/R) · (Δf - deadband) / f_nom.
        Actif uniquement en GRID_CONNECTED. Bande morte ±DROOP_DEADBAND_HZ.
        """
        if not DROOP_ENABLED or self.machine_state != "GRID_CONNECTED":
            return 0.0
        df = freq_hz - DROOP_FREQ_REF_HZ
        if abs(df) < DROOP_DEADBAND_HZ:
            return 0.0
        df_eff = df - math.copysign(DROOP_DEADBAND_HZ, df)
        delta_mw = -(NOMINAL["active_power"] / DROOP_R) * (df_eff / DROOP_FREQ_REF_HZ)
        return max(-DROOP_MAX_DELTA_MW, min(DROOP_MAX_DELTA_MW, delta_mw))

    def _update_pressure_pid(self, dt: float, current_pressure_hp_bar: float):
        """PID pression HP actif quand regulation_target == 'PRESSURE'.

        Sens : V1↑ → débit admis ↑ → pression header HP ↓ (boiler limité).
        Pour obtenir ce comportement avec un PID standard (error = sp - meas),
        on échange setpoint et measured : error = current - sp.
        → pression trop haute → error > 0 → output ↑ → V1 ouvre → pression ↓.
        """
        sp = self._setpoint_pressure_hp_bar or PRESSURE_HP_SETPOINT_BAR
        # Swap intentionnel : setpoint=current, measurement=sp → error = current - sp
        v1_target = self._pid_pressure.compute(current_pressure_hp_bar, sp, dt)
        self._last_pid_output = round(v1_target, 2)
        self._last_pid_error  = round(current_pressure_hp_bar - sp, 3)
        result = valve_controller.set_valve("v1", v1_target)
        if not result.get("accepted"):
            self._pid_pressure._integral -= self._pid_pressure.error * dt

    def _check_auto_transitions(self, current_speed_rpm: float, current_power_mw: float):
        """Transitions automatiques du MachineState pendant les séquences."""
        nominal_rpm = NOMINAL["turbine_speed"]

        # ── Orchestrateur séquence AUTO (STOPPED → GRID_CONNECTED pas-à-pas) ──────
        if (self.mode == "AUTO"
                and self._sequence_state == "STARTING"
                and self.machine_state in ("STOPPED", "ROLLING", "SYNCHRONIZING")):
            now = time.time()
            phase = self.startup_phase
            t_in_phase = now - self._phase_entered_at  # _phase_entered_at mis à jour par _advance_phase

            if phase == "PRE_CHECKS" and t_in_phase >= AUTO_STEP_DELAY_BARRAGE_S:
                self.cmd_open_barrage(operator="AUTO")

            elif phase == "BARRAGE_OPENED" and t_in_phase >= AUTO_STEP_DELAY_ESV_S:
                # Bypass interlock vitesse (vireur virtuel en AUTO)
                valve_controller.open_esv()
                self._advance_phase("ESV_OPENED")
                data_manager.log_operator_action(
                    user="AUTO", action_type="STARTUP_PHASE",
                    target="esv", value_before="BARRAGE_OPENED", value_after="ESV_OPENED",
                )

            elif phase == "ESV_OPENED" and t_in_phase >= AUTO_STEP_DELAY_V1_S:
                self.cmd_open_v1(operator="AUTO")  # entre ROLLING, ouvre V1/V2/V3

            elif phase == "READY_TO_EXCITE" and t_in_phase >= AUTO_STEP_DELAY_EXCITE_S:
                self.cmd_excite(operator="AUTO")

            elif phase == "EXCITED" and t_in_phase >= AUTO_STEP_DELAY_SYNC_ARM_S:
                if abs(self._last_speed_rpm_cache - nominal_rpm) <= SPEED_SYNC_THRESHOLD_RPM:
                    self.cmd_synchronize_arm(operator="AUTO")

            elif phase == "SYNCHRONIZING":
                result = self.cmd_couple_grid(operator="AUTO")
                if result.get("accepted"):
                    # Réinitialise le timer de rampe MW maintenant que la machine est couplée
                    self._sequence_t0 = time.time()

            return  # pas de double-transition dans le même tick

        # ── Transitions standard ROLLING / SYNCHRONIZING / GRID_CONNECTED ─────────
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
            # Exige AVR=OFF ou trip pour éviter transition parasite si excitation transitoirement nulle
            if (self._sequence_state == "IDLE"
                    and self._sequence_name is None
                    and current_power_mw < 0.5
                    and valve_controller._valves["v1"].current < 2.0):
                try:
                    from simulation.avr_controller import avr_controller as _avr_check
                    avr_off = _avr_check.mode == "OFF"
                except Exception:
                    avr_off = True
                if avr_off or self.tripped:
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
        # Seed les PIDs puissance et pression sur la position V1 courante (bumpless)
        current_v1 = valve_controller._valves["v1"].target
        seed_power    = current_v1 / self._pid.ki if self._pid.ki > 0 else current_v1
        seed_pressure = current_v1 / self._pid_pressure.ki if self._pid_pressure.ki > 0 else current_v1
        self._pid.seed(seed_power)
        self._pid_pressure.seed(seed_pressure)
        # Consigne puissance nominale si aucune fixée
        if self._setpoint_power_mw is None:
            self._setpoint_power_mw = NOMINAL["active_power"]
        # Consigne pression nominale si aucune fixée
        if self._setpoint_pressure_hp_bar is None:
            self._setpoint_pressure_hp_bar = PRESSURE_HP_SETPOINT_BAR
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
        self._pid_pressure.reset()
        self._sync_entry_time = None
        self._setpoint_power_mw        = None
        self._setpoint_speed_rpm       = None
        self._setpoint_pressure_hp_bar = None
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
    # PHASE DE DÉMARRAGE MANUEL
    # ──────────────────────────────────────────────────────

    def _advance_phase(self, new_phase: str, message: str | None = None) -> None:
        self.startup_phase     = new_phase
        self._phase_entered_at = time.time()
        self._phase_message    = message
        logger.info(f"[Controller] startup_phase → {new_phase}")

    def _tick_manual_phase(self, dt: float, speed_rpm: float) -> None:
        """Transitions passives (automatiques) en mode MANUAL — ne touche pas aux vannes."""
        nominal = NOMINAL["turbine_speed"]
        if self.startup_phase == "V1_OPENING":
            if valve_controller._valves["v1"].current >= 80.0:
                valve_controller.set_valve("bp_admit", 0.0)  # handover BP→HP
                self._advance_phase("ACCELERATING")
        elif self.startup_phase == "ACCELERATING":
            if abs(speed_rpm - nominal) < SPEED_SYNC_THRESHOLD_RPM:
                self._advance_phase("READY_TO_EXCITE")

    def cmd_open_barrage(self, operator: str = "Opérateur") -> dict:
        """Étape 2 : ouvre la vanne vapeur de barrage (bp_admit → 100%)."""
        if self.tripped:
            return {"accepted": False, "message": "Trip actif — effectuez un Reset Trip."}
        if self.startup_phase != "PRE_CHECKS":
            return {"accepted": False, "message": f"Phase actuelle : {self.startup_phase}. Séquence non en PRE_CHECKS."}
        valve_controller.set_valve("bp_admit", 100.0)
        self._advance_phase("BARRAGE_OPENED")
        data_manager.log_operator_action(
            user=operator, action_type="STARTUP_PHASE",
            target="bp_admit", value_before="PRE_CHECKS", value_after="BARRAGE_OPENED",
        )
        return {"accepted": True, "message": "Vapeur de barrage ouverte — attendre vitesse ~3000 RPM."}

    def cmd_open_esv(self, operator: str = "Opérateur") -> dict:
        """Étape 3 : ouvre l'ESV (soupape d'arrêt HP) — interlock vitesse ≥ ESV_MIN_SPEED_RPM."""
        if self.tripped:
            return {"accepted": False, "message": "Trip actif — effectuez un Reset Trip."}
        if self.startup_phase != "BARRAGE_OPENED":
            return {"accepted": False, "message": f"Phase actuelle : {self.startup_phase}. Requise : BARRAGE_OPENED."}
        if self._last_speed_rpm_cache < ESV_MIN_SPEED_RPM:
            return {"accepted": False,
                    "message": f"Vitesse insuffisante ({self._last_speed_rpm_cache:.0f} < {ESV_MIN_SPEED_RPM:.0f} RPM). Attendez la montée du barrage."}
        valve_controller.open_esv()
        self._advance_phase("ESV_OPENED")
        data_manager.log_operator_action(
            user=operator, action_type="STARTUP_PHASE",
            target="esv", value_before="BARRAGE_OPENED", value_after="ESV_OPENED",
        )
        return {"accepted": True, "message": "ESV ouverte — admission HP disponible. Ouvrez V1."}

    def cmd_open_v1(self, operator: str = "Opérateur") -> dict:
        """Étape 4 : ouvre V1 (admission HP) — interlock ESV ouverte."""
        if self.tripped:
            return {"accepted": False, "message": "Trip actif."}
        if self.startup_phase != "ESV_OPENED":
            return {"accepted": False, "message": f"Phase actuelle : {self.startup_phase}. Requise : ESV_OPENED."}
        if not valve_controller.esv_open:
            return {"accepted": False, "message": "Sécurité : V1 requiert l'ESV (admission HP) ouverte."}
        # Transition machine STOPPED → ROLLING (active la dynamique rotor)
        self._enter_rolling(operator=operator)
        # Ouvrir les 3 vannes de réglage HP
        valve_controller.set_valve("v1", 100.0)
        valve_controller.set_valve("v2", 100.0)
        valve_controller.set_valve("v3", 100.0)
        
        self._advance_phase("V1_OPENING")
        data_manager.log_operator_action(
            user=operator, action_type="STARTUP_PHASE",
            target="v1", value_before="ESV_OPENED", value_after="V1_OPENING",
        )
        return {"accepted": True, "message": "V1 en ouverture — phase ACCÉLÉRATION en cours."}

    def cmd_excite(self, operator: str = "Opérateur") -> dict:
        """Étape 5 : active l'AVR (excitation alternateur)."""
        if self.startup_phase != "READY_TO_EXCITE":
            return {"accepted": False, "message": f"Phase actuelle : {self.startup_phase}. Requise : READY_TO_EXCITE."}
        try:
            from simulation.avr_controller import avr_controller as _avr
            _avr.set_mode("VOLTAGE", operator=operator)
        except Exception as e:
            return {"accepted": False, "message": f"Erreur AVR : {e}"}
        self._advance_phase("EXCITED")
        data_manager.log_operator_action(
            user=operator, action_type="STARTUP_PHASE",
            target="avr", value_before="READY_TO_EXCITE", value_after="EXCITED",
        )
        return {"accepted": True, "message": "AVR activé — tension en montée vers consigne."}

    def cmd_synchronize_arm(self, operator: str = "Opérateur") -> dict:
        """Étape 6 : arme la synchronisation (ROLLING → SYNCHRONIZING)."""
        if self.startup_phase != "EXCITED":
            return {"accepted": False, "message": f"Phase actuelle : {self.startup_phase}. Requise : EXCITED."}
        nominal = NOMINAL["turbine_speed"]
        if abs(self._last_speed_rpm_cache - nominal) > SPEED_SYNC_THRESHOLD_RPM:
            delta = abs(self._last_speed_rpm_cache - nominal)
            return {"accepted": False, "message": f"Vitesse hors fenêtre synchrone (Δ={delta:.0f} RPM > {SPEED_SYNC_THRESHOLD_RPM} RPM)."}
        self._enter_synchronizing()
        self._advance_phase("SYNCHRONIZING")
        data_manager.log_operator_action(
            user=operator, action_type="STARTUP_PHASE",
            target="machine_state", value_before="EXCITED", value_after="SYNCHRONIZING",
        )
        return {"accepted": True, "message": "Synchronisation armée — cliquez Coupler réseau pour finaliser."}

    def cmd_couple_grid(self, operator: str = "Opérateur") -> dict:
        """Étape 7 : couplage réseau (SYNCHRONIZING → GRID_CONNECTED).

        Pré-conditions de synchronisation :
          - Phase : SYNCHRONIZING
          - machine_state : SYNCHRONIZING
          - Excitation : AVR actif (mode != OFF)
          - Fréquence   : 49.9 – 50.1 Hz
          - Vitesse     : dans fenêtre SPEED_SYNC_THRESHOLD_RPM
        """
        if self.startup_phase != "SYNCHRONIZING":
            return {"accepted": False, "message": f"Phase actuelle : {self.startup_phase}. Requise : SYNCHRONIZING."}
        if self.machine_state == "GRID_CONNECTED":
            return {"accepted": False, "message": "Machine déjà couplée au réseau."}
        if self.machine_state != "SYNCHRONIZING":
            return {"accepted": False, "message": f"État machine : {self.machine_state}. Requis : SYNCHRONIZING."}
        # Vérification excitation
        try:
            from simulation.avr_controller import avr_controller as _avr
            if _avr.mode == "OFF":
                return {"accepted": False, "message": "Excitation requise avant couplage réseau. Activez l'AVR."}
        except Exception:
            pass
        # Vérification fréquence
        try:
            from simulation.dynamics import rotor_dynamics as _rotor
            freq = _rotor.frequency_hz
            f_lo = 50.0 - GRID_COUPLE_FREQ_TOL_HZ
            f_hi = 50.0 + GRID_COUPLE_FREQ_TOL_HZ
            if not (f_lo <= freq <= f_hi):
                logger.warning("[Couple] Rejet fréquence : %.3f Hz (fenêtre [%.1f – %.1f])", freq, f_lo, f_hi)
                return {"accepted": False, "message": f"Fréquence hors fenêtre ({freq:.2f} Hz). Plage requise : {f_lo:.1f} – {f_hi:.1f} Hz."}
        except Exception:
            pass
        self._enter_grid_connected(operator=operator)
        self._advance_phase("GRID_CONNECTED")
        data_manager.log_operator_action(
            user=operator, action_type="STARTUP_PHASE",
            target="machine_state", value_before="SYNCHRONIZING", value_after="GRID_CONNECTED",
        )
        return {"accepted": True, "message": "Machine couplée au réseau — PID puissance actif."}

    # ──────────────────────────────────────────────────────
    # LOGIQUE SÉQUENCE PUISSANCE
    # ──────────────────────────────────────────────────────

    def _compute_sequence_setpoint(self, current_power_mw: float) -> float | None:
        """Consigne puissance interpolée (séquence) ou fixe."""
        if self._sequence_state in ("STARTING", "STOPPING") and self._sequence_t0 is not None:
            # Pendant ROLLING ou démarrage en cours (avant couplage), puissance non pilotée
            if self.machine_state in ("ROLLING", "STOPPED"):
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
            "startup_phase":       self.startup_phase,
            "startup_phase_message": self._phase_message,
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
            # Gains PID pression HP
            "pid_pressure_kp":     self._pid_pressure.kp,
            "pid_pressure_ki":     self._pid_pressure.ki,
            "pid_pressure_kd":     self._pid_pressure.kd,
            # Régulation pression HP (Phase 0 — A.1)
            "regulation_target":        self._regulation_target,
            "setpoint_pressure_hp_bar": self._setpoint_pressure_hp_bar,
            # Droop primaire (Phase 1 — B.1)
            "droop_enabled":            DROOP_ENABLED,
            "droop_r":                  DROOP_R,
            "droop_offset_mw":          self._last_droop_offset_mw,
            "freq_meas_hz":             round(self._last_freq_hz_cache, 3),
        }

    def get_state_dict(self) -> dict:
        """État complet pour GET /control/state."""
        from simulation.avr_controller import avr_controller
        from simulation.dynamics import rotor_dynamics
        return {
            **self.snapshot(),
            "setpoint_pressure_hp_bar": self._setpoint_pressure_hp_bar,
            "pid_integral":             round(self._pid._integral, 4),
            "valve_state":              valve_controller.get_state(),
            "grid_frequency":           rotor_dynamics.frequency_hz,
            "esv_open":                 valve_controller.esv_open,
            **avr_controller.snapshot(),
        }


controller = Controller()
