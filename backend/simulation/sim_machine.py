"""
simulation/sim_machine.py — Machine simulée « fork » indépendante.

Active uniquement pendant un scénario (piloté par FakeAPI). Possède ses propres
ValveController / RotorDynamics / ProtectionSystem / PID puissance, copiés depuis
la machine réelle au moment du fork. Un scénario peut ainsi réguler ET tripper la
machine simulée sans perturber la machine réelle (dashboard).

Expose l'interface minimale attendue par ProtectionSystem.check_all() :
  tripped, machine_state, _grid_connected_at, emergency_trip(), disconnect_from_grid()
"""

import logging

from simulation.pid import PID
from simulation.valve_controller import ValveController
from simulation.dynamics import RotorDynamics
from simulation.protection import ProtectionSystem
from simulation.avr_controller import AVRController
from core.config import PID_POWER_OUT_MIN, PID_POWER_OUT_MAX, NOMINAL

logger = logging.getLogger("gta.sim_machine")


class SimMachine:
    def __init__(self):
        self.valves     = ValveController()
        self.rotor      = RotorDynamics()
        self.protection = ProtectionSystem()
        self.pid        = PID(kp=0.0, ki=0.0, kd=0.0, out_min=PID_POWER_OUT_MIN, out_max=PID_POWER_OUT_MAX)
        
        self.avr        = AVRController()
        # Offsets manuels lubrification (sandbox) — appliqués sur computed_sim uniquement
        self.lube_press_offset: float = 0.0
        self.lube_temp_offset:  float = 0.0

        self.mode               = "AUTO"
        self.machine_state      = "GRID_CONNECTED"
        self.tripped            = False
        self._grid_connected_at = None
        self.setpoint_power_mw  = NOMINAL["active_power"]

    # ── Fork depuis la machine réelle ──────────────────────────────
    def fork_from(self, controller, valve_controller,rotor_dynamics, avr_controller):
        self.machine_state      = controller.machine_state
        self.tripped            = controller.tripped
        self.mode               = controller.mode
        self._grid_connected_at = getattr(controller, "_grid_connected_at", None)
        sp = getattr(controller, "_setpoint_power_mw", None)
        self.setpoint_power_mw  = sp if sp is not None else NOMINAL["active_power"]
        # PID puissance : copie gains + intégrale
        self.pid.kp = controller._pid.kp
        self.pid.ki = controller._pid.ki
        self.pid.kd = controller._pid.kd
        self.pid._integral   = controller._pid._integral
        self.pid._prev_error = controller._pid._prev_error

        # Vannes : copie positions + cibles + ESV
        for vid, vstate in valve_controller._valves.items():
            self.valves._valves[vid].current = vstate.current
            self.valves._valves[vid].target  = vstate.target
        self.valves._esv_open = valve_controller._esv_open

        # Rotor : copie vitesse + verrou réseau
        self.rotor.omega_rad_s  = rotor_dynamics.omega_rad_s
        self.rotor._grid_locked = rotor_dynamics._grid_locked

        # AVR : copie mode, gains, consignes, état d'excitation + limiteurs
        self.avr.mode           = avr_controller.mode
        self.avr.k_a            = avr_controller.k_a
        self.avr.t_a            = avr_controller.t_a
        self.avr.v_set_kv       = avr_controller.v_set_kv
        self.avr.cosphi_set     = avr_controller.cosphi_set
        self.avr.e_fd_pu        = avr_controller.e_fd_pu
        self.avr.e_fd_manual    = avr_controller.e_fd_manual
        self.avr.saturated      = avr_controller.saturated
        self.avr.oel_active     = avr_controller.oel_active
        self.avr.uel_active     = avr_controller.uel_active
        self.avr.scl_active     = avr_controller.scl_active
        self.avr._oel_timer     = avr_controller._oel_timer
        self.avr._scl_timer     = avr_controller._scl_timer
        self.avr._last_v_term   = avr_controller._last_v_term
        self.avr._last_cosphi   = avr_controller._last_cosphi
        self.avr._last_i_stator = avr_controller._last_i_stator

        logger.info("[SimMachine] Fork — état=%s V1=%.1f%% vitesse=%.0f RPM AVR=%s",
                    self.machine_state, self.valves.v1, self.rotor.speed_rpm, self.avr.mode)

    # ── Interface attendue par ProtectionSystem ────
    def emergency_trip(self, operator="SIM"):
        if self.tripped:
            return
        self.tripped            = True
        self.machine_state      = "TRIPPED"
        self.mode               = "MANUAL"
        self._grid_connected_at = None
        self.pid.reset()
        self.valves.emergency_close()
        self.rotor.unlock_from_grid()
        logger.warning("[SimMachine] TRIP simulé (%s)", operator)

    def disconnect_from_grid(self, operator="SIM"):
        if self.machine_state != "GRID_CONNECTED":
            return
        self.machine_state      = "ROLLING"
        self._grid_connected_at = None
        self.pid.reset()
        self.valves.close_esv()
        for vid in ("v1", "v2", "v3"):
            self.valves.set_valve(vid, 0.0)
        self.rotor.unlock_from_grid()
        logger.warning("[SimMachine] Découplage réseau simulé (%s)", operator)

    # ── Tick supervision (PID puissance + rampe vannes) ────────────
    def step(self, dt, current_power_mw):
        if not self.tripped and self.machine_state == "GRID_CONNECTED" and self.mode == "AUTO":
            sp = self.setpoint_power_mw if self.setpoint_power_mw is not None else NOMINAL["active_power"]
            v1_target = self.pid.compute(sp, current_power_mw, dt)
            result = self.valves.set_valve("v1", v1_target)
            if not result.get("accepted"):
                self.pid._integral -= self.pid.error
        self.valves.update(dt)