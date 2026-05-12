"""
simulation/avr_controller.py — Régulateur d'excitation AVR (IEEE Type 1 simplifié)

Modèle 1er ordre :  T_A · dE_fd/dt = K_A · (consigne − mesure) − E_fd
Discrétisation ZOH analytique (stable pour tout dt, même dt >> T_A = 50 ms) :
    α = exp(−dt / T_A)
    E_fd(k+1) = E_fd(k)·α + target·(1−α)

Modes :
  OFF     → AVR désactivé, branche algébrique legacy active dans physics_model.
  VOLTAGE → régule V_term vers v_set_kv.
  COSPHI  → régule cos φ vers cosphi_set.
  MANUAL  → E_fd piloté directement par l'opérateur (debug / pédagogique).

Singleton avr_controller, appelé depuis fake_api._generate_dual()
après controller.update() et avant valve_controller.update().
"""

import math
import logging

from core.config import (
    AVR_K_A, AVR_T_A, AVR_E_FD_MIN, AVR_E_FD_MAX,
    AVR_VOLTAGE_SETPOINT, AVR_COSPHI_SETPOINT, NOMINAL,
)
from services.data_manager import data_manager

logger = logging.getLogger("gta.avr")


class AVRController:
    """Régulateur d'excitation IEEE Type 1 simplifié — singleton."""

    def __init__(self):
        self.mode        = "VOLTAGE"          # OFF / VOLTAGE / COSPHI / MANUAL
        self.k_a         = AVR_K_A
        self.t_a         = AVR_T_A
        self.v_set_kv    = AVR_VOLTAGE_SETPOINT
        self.cosphi_set  = AVR_COSPHI_SETPOINT
        self.e_fd_pu     = 1.0                # tension excitation initiale (p.u. → équilibre nominal)
        self.e_fd_manual = 1.0                # valeur opérateur en mode MANUAL
        self.saturated   = False

        self._last_v_term = float(NOMINAL.get("voltage", 10.5))
        self._last_cosphi = float(NOMINAL.get("power_factor", 0.85))

    # ──────────────────────────────────────────────────────
    # TICK — appelée depuis fake_api._generate_dual()
    # ──────────────────────────────────────────────────────

    def update(self, dt: float, v_term_kv: float, cosphi: float) -> None:
        """Intègre E_fd pour un tick de durée dt (s). Utilise les mesures du tick précédent."""
        self._last_v_term = v_term_kv
        self._last_cosphi = cosphi

        if self.mode == "OFF":
            return

        if self.mode == "MANUAL":
            clamped = max(AVR_E_FD_MIN, min(AVR_E_FD_MAX, self.e_fd_manual))
            self.saturated = (clamped != self.e_fd_manual)
            self.e_fd_pu   = clamped
            return

        # Erreur régulateur
        if self.mode == "VOLTAGE":
            # + : V_term sous consigne → augmenter E_fd → augmenter V_term
            v_ref  = float(NOMINAL.get("voltage", 10.5))
            error  = (self.v_set_kv - v_term_kv) / v_ref   # normalisé p.u.
        else:  # COSPHI
            # Convention : error = mesure - consigne
            # cos φ < consigne → error < 0 → E_fd diminue → Q diminue → cos φ monte ✓
            error = cosphi - self.cosphi_set

        # Cible E_fd (point d'équilibre = 1.0 p.u. + correction proportionnelle)
        target = 1.0 + self.k_a * error / 100.0

        # ZOH analytique : α = exp(−dt / T_A)
        alpha    = math.exp(-dt / max(self.t_a, 1e-3))
        e_fd_new = self.e_fd_pu * alpha + target * (1.0 - alpha)

        clamped        = max(AVR_E_FD_MIN, min(AVR_E_FD_MAX, e_fd_new))
        self.saturated = (clamped != e_fd_new)
        self.e_fd_pu   = clamped

    # ──────────────────────────────────────────────────────
    # COMMANDES (appelées depuis les routes HTTP)
    # ──────────────────────────────────────────────────────

    def set_mode(self, mode: str, operator: str = "Opérateur") -> dict:
        allowed = {"OFF", "VOLTAGE", "COSPHI", "MANUAL"}
        if mode not in allowed:
            return {"accepted": False, "message": f"Mode AVR invalide '{mode}'. Valeurs : {allowed}"}
        before = self.mode
        self.mode = mode
        # En sortie de MANUAL, resynchroniser e_fd_manual sur la valeur courante
        if mode != "MANUAL":
            self.e_fd_manual = self.e_fd_pu
        data_manager.log_operator_action(
            user=operator, action_type="AVR_MODE_CHANGE",
            target="avr_mode", value_before=before, value_after=mode,
        )
        logger.info(f"[AVR] Mode → {mode}")
        return {"accepted": True, "message": f"AVR mode : {before} → {mode}"}

    def set_setpoint(
        self,
        voltage_kv: float | None = None,
        cosphi: float | None = None,
        operator: str = "Opérateur",
    ) -> dict:
        import json
        before = json.dumps({"voltage_kv": self.v_set_kv, "cosphi": self.cosphi_set})
        if voltage_kv is not None:
            self.v_set_kv = float(voltage_kv)
        if cosphi is not None:
            self.cosphi_set = float(cosphi)
        after = json.dumps({"voltage_kv": self.v_set_kv, "cosphi": self.cosphi_set})
        data_manager.log_operator_action(
            user=operator, action_type="AVR_SETPOINT_CHANGE",
            target="avr_setpoint", value_before=before, value_after=after,
        )
        return {"accepted": True, "setpoints": {"voltage_kv": self.v_set_kv, "cosphi": self.cosphi_set}}

    def set_gains(self, k_a: float, t_a: float, operator: str = "Opérateur") -> dict:
        import json
        before = json.dumps({"k_a": self.k_a, "t_a": self.t_a})
        self.k_a = float(k_a)
        self.t_a = max(1e-3, float(t_a))
        after = json.dumps({"k_a": self.k_a, "t_a": self.t_a})
        data_manager.log_operator_action(
            user=operator, action_type="AVR_GAINS_CHANGE",
            target="avr_gains", value_before=before, value_after=after,
        )
        return {"accepted": True, "k_a": self.k_a, "t_a": self.t_a}

    def set_e_fd_manual(self, e_fd: float, operator: str = "Opérateur") -> dict:
        before = round(self.e_fd_manual, 4)
        self.e_fd_manual = float(e_fd)
        data_manager.log_operator_action(
            user=operator, action_type="AVR_EFD_MANUAL",
            target="avr_e_fd_manual",
            value_before=str(before), value_after=str(round(e_fd, 4)),
        )
        return {"accepted": True, "e_fd_manual": self.e_fd_manual}

    # ──────────────────────────────────────────────────────
    # SNAPSHOT — fusionné dans computed_sim et /control/state
    # ──────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "avr_mode":      self.mode,
            "avr_setpoint":  self.v_set_kv if self.mode != "COSPHI" else self.cosphi_set,
            "avr_e_fd_pu":   round(self.e_fd_pu, 4),
            "avr_saturated": self.saturated,
            "avr_k_a":       self.k_a,
            "avr_t_a":       self.t_a,
            "avr_v_term":    round(self._last_v_term, 3),
            "avr_cosphi":    round(self._last_cosphi, 3),
        }


avr_controller = AVRController()
