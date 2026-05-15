"""
simulation/attemperator.py — Désurchauffeur (PID T° vapeur HP → injection eau)

Module amont du compute_all() physics :
  - PID T° : si T_in > T_sp → injection ouvre → T_HP baisse.
    Convention swap args : compute(T_in, T_sp, dt) → error = T_in - T_sp > 0 → output ↑.
  - Sortie 0-100 % → ΔT = -injection/100 * ATTEMP_MAX_COOLING_C
  - Filtre 1er ordre (τ = ATTEMP_TAU_S) pour lisser les à-coups
  - Clamp sortie : T_out >= 380 °C (marge de sécurité IAPWS97 à 60 bar)

Singleton attemperator, appelé depuis fake_api._generate_dual() entre
self._add_noise(state_sim) et physics.compute_all(...).
"""

import math
import logging

from core.config import (
    ATTEMPERATOR_ENABLED,
    ATTEMP_KP, ATTEMP_KI, ATTEMP_KD,
    ATTEMP_OUT_MIN, ATTEMP_OUT_MAX,
    ATTEMP_T_HP_SETPOINT_C,
    ATTEMP_MAX_COOLING_C,
    ATTEMP_TAU_S,
)
from simulation.pid import PID

logger = logging.getLogger("gta.attemperator")

_T_OUT_MIN_C = 380.0   # plancher de sécurité (IAPWS97 : saturation 60 bar ≈ 275 °C, marge)


class Attemperator:
    """Désurchauffeur vapeur HP — singleton."""

    def __init__(self):
        self._pid = PID(
            kp=ATTEMP_KP, ki=ATTEMP_KI, kd=ATTEMP_KD,
            out_min=ATTEMP_OUT_MIN, out_max=ATTEMP_OUT_MAX,
        )
        self._injection_pct: float = 0.0
        self._injection_raw_pct: float = 0.0
        self.setpoint_c: float = ATTEMP_T_HP_SETPOINT_C
        self.enabled: bool = ATTEMPERATOR_ENABLED

    def step(self, t_in_c: float, dt: float) -> tuple[float, float]:
        """Calcule (t_out_c, injection_pct) pour un tick de durée dt (s).

        Sens : injection ↑ → eau pulvérisée ↑ → T_HP ↓.
        Swap args pour avoir error = T_in - T_sp → output ↑ si T trop haute.
        """
        if not self.enabled:
            self._injection_pct = 0.0
            self._injection_raw_pct = 0.0
            return t_in_c, 0.0

        # Swap intentionnel : setpoint=T_in, measurement=T_sp → error = T_in - T_sp
        raw = self._pid.compute(t_in_c, self.setpoint_c, dt)
        self._injection_raw_pct = raw

        # Filtre 1er ordre (lisse les à-coups thermiques)
        alpha = math.exp(-dt / max(ATTEMP_TAU_S, 1e-3))
        self._injection_pct = self._injection_pct * alpha + raw * (1.0 - alpha)

        delta_t = -ATTEMP_MAX_COOLING_C * (self._injection_pct / 100.0)
        t_out = max(_T_OUT_MIN_C, t_in_c + delta_t)
        return t_out, self._injection_pct

    def set_setpoint(self, value_c: float, operator: str = "Opérateur") -> dict:
        from services.data_manager import data_manager
        before = self.setpoint_c
        self.setpoint_c = float(value_c)
        data_manager.log_operator_action(
            user=operator, action_type="ATTEMP_SETPOINT_CHANGE",
            target="attemp_t_hp_setpoint",
            value_before=str(round(before, 1)),
            value_after=str(round(self.setpoint_c, 1)),
        )
        return {"accepted": True, "setpoint_c": self.setpoint_c}

    def set_enabled(self, enabled: bool, operator: str = "Opérateur") -> dict:
        from services.data_manager import data_manager
        before = self.enabled
        self.enabled = bool(enabled)
        data_manager.log_operator_action(
            user=operator, action_type="ATTEMP_ENABLE",
            target="attemp_enabled",
            value_before=str(before), value_after=str(self.enabled),
        )
        return {"accepted": True, "enabled": self.enabled}

    def snapshot(self) -> dict:
        return {
            "attemp_enabled":       self.enabled,
            "attemp_setpoint_c":    round(self.setpoint_c, 1),
            "attemp_injection_pct": round(self._injection_pct, 2),
        }


attemperator = Attemperator()
