"""
simulation/condenser.py — Condenseur (hotwell + groupe vide)

Deux boucles de régulation indépendantes :
  1. Niveau hotwell (%)  ← contrôlé par pompe extraction (sortie %)
       apport  : steam_flow_condenser (T/h) condensée → eau dans la hotwell
       retrait : pompe extraction
  2. Vide condenseur (mbar)  ← contrôlé par éjecteur vapeur (sortie %)
       dégradation : charge vapeur → vide se dégrade (mbar ↑)
       récupération : éjecteur retire les incondensables

Modèle dynamique 1er ordre — pas IAPWS, variables d'état internes indépendantes
du pressure_condenser physique (0.0064 bar hardcodé dans physics_model).

Singleton condenser, appelé dans fake_api._generate_dual() après compute_all().
"""

import logging

from core.config import (
    CONDENSER_ENABLED,
    COND_LEVEL_KP, COND_LEVEL_KI, COND_LEVEL_KD,
    COND_LEVEL_SETPOINT_PCT, COND_LEVEL_OUT_MIN, COND_LEVEL_OUT_MAX,
    COND_VACUUM_KP, COND_VACUUM_KI, COND_VACUUM_KD,
    COND_VACUUM_SETPOINT_MBAR, COND_VACUUM_OUT_MIN, COND_VACUUM_OUT_MAX,
    COND_INFLOW_GAIN_PCT_PER_TH, COND_PUMP_GAIN_PCT_PER_PCT,
    COND_VACUUM_LOAD_MBAR_PER_TH, COND_VACUUM_EJECTOR_MBAR_PER_PCT,
)
from simulation.pid import PID

logger = logging.getLogger("gta.condenser")


class Condenser:
    """Condenseur avec 2 boucles PID — singleton."""

    def __init__(self):
        # PID niveau hotwell → pompe extraction
        self._pid_level = PID(
            kp=COND_LEVEL_KP, ki=COND_LEVEL_KI, kd=COND_LEVEL_KD,
            out_min=COND_LEVEL_OUT_MIN, out_max=COND_LEVEL_OUT_MAX,
        )
        # PID vide → éjecteur (swap args : error = vacuum - sp → output ↑ si vide dégradé)
        self._pid_vacuum = PID(
            kp=COND_VACUUM_KP, ki=COND_VACUUM_KI, kd=COND_VACUUM_KD,
            out_min=COND_VACUUM_OUT_MIN, out_max=COND_VACUUM_OUT_MAX,
        )
        self.level_pct: float = 50.0
        self.vacuum_mbar: float = 64.0
        self.pump_pct: float = 50.0
        self.ejector_pct: float = 50.0
        self.level_setpoint_pct: float = COND_LEVEL_SETPOINT_PCT
        self.vacuum_setpoint_mbar: float = COND_VACUUM_SETPOINT_MBAR
        self.enabled: bool = CONDENSER_ENABLED

    def step(self, dt: float, steam_flow_condenser_th: float) -> dict:
        """Intègre niveau et vide pour un tick de durée dt (s).

        Niveau : d_level = (INFLOW_GAIN · flow - PUMP_GAIN · pump_pct) · dt
        Vide   : d_vac   = (LOAD_GAIN · flow - EJECTOR_GAIN · ejector_pct) · dt
        """
        if not self.enabled:
            return self.snapshot()

        # ── Niveau hotwell ──
        # Swap args : compute(level, sp, dt) → error = level - sp > 0 si niveau trop haut → pompe ouvre.
        self.pump_pct = self._pid_level.compute(self.level_pct, self.level_setpoint_pct, dt)
        d_level = (
            COND_INFLOW_GAIN_PCT_PER_TH * steam_flow_condenser_th
            - COND_PUMP_GAIN_PCT_PER_PCT * self.pump_pct
        ) * dt
        self.level_pct = max(0.0, min(100.0, self.level_pct + d_level))

        # ── Vide condenseur ──
        # Swap args : compute(vacuum, sp, dt) → error = vacuum - sp > 0 si vide dégradé → éjecteur ouvre.
        self.ejector_pct = self._pid_vacuum.compute(self.vacuum_mbar, self.vacuum_setpoint_mbar, dt)
        d_vac = (
            COND_VACUUM_LOAD_MBAR_PER_TH * steam_flow_condenser_th
            - COND_VACUUM_EJECTOR_MBAR_PER_PCT * self.ejector_pct
        ) * dt
        self.vacuum_mbar = max(1.0, min(200.0, self.vacuum_mbar + d_vac))

        return self.snapshot()

    def set_level_setpoint(self, value_pct: float, operator: str = "Opérateur") -> dict:
        from services.data_manager import data_manager
        before = self.level_setpoint_pct
        self.level_setpoint_pct = float(value_pct)
        data_manager.log_operator_action(
            user=operator, action_type="COND_LEVEL_SP_CHANGE",
            target="cond_level_sp",
            value_before=str(round(before, 1)),
            value_after=str(round(self.level_setpoint_pct, 1)),
        )
        return {"accepted": True, "setpoint_pct": self.level_setpoint_pct}

    def set_vacuum_setpoint(self, value_mbar: float, operator: str = "Opérateur") -> dict:
        from services.data_manager import data_manager
        before = self.vacuum_setpoint_mbar
        self.vacuum_setpoint_mbar = float(value_mbar)
        data_manager.log_operator_action(
            user=operator, action_type="COND_VACUUM_SP_CHANGE",
            target="cond_vacuum_sp",
            value_before=str(round(before, 1)),
            value_after=str(round(self.vacuum_setpoint_mbar, 1)),
        )
        return {"accepted": True, "setpoint_mbar": self.vacuum_setpoint_mbar}

    def snapshot(self) -> dict:
        return {
            "condenser_enabled":          self.enabled,
            "condenser_level_pct":        round(self.level_pct, 2),
            "condenser_vacuum_mbar":      round(self.vacuum_mbar, 2),
            "condenser_pump_pct":         round(self.pump_pct, 2),
            "condenser_ejector_pct":      round(self.ejector_pct, 2),
            "condenser_level_setpoint":   round(self.level_setpoint_pct, 1),
            "condenser_vacuum_setpoint":  round(self.vacuum_setpoint_mbar, 1),
        }


condenser = Condenser()
