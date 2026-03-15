"""
simulation/valve_controller.py — Contrôleur des 5 vannes du GTA (régime permanent)

Architecture :
  V1  — Admission vapeur HP principale (80% du débit)
  V2  — Équilibrage mécanique turbine (~7%) — pas dans le bilan thermo
  V3  — Équilibrage mécanique turbine (~7%) — pas dans le bilan thermo
  MP  — Extraction vapeur MP vers barillet
  BP  — Sortie vapeur BP vers condenseur (min 5% sécurité)

Règles de sécurité intégrées :
  - valve_bp ≥ 5% si V1 > 10% (pression condenseur)
  - valve_mp < 80% si active_power > 22 MW (risque surpression barillet)
  - Fermeture rapide V1 → alerte choc thermique
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("gta.valves")


@dataclass
class ValveConfig:
    name:         str
    min_opening:  float = 0.0
    max_opening:  float = 100.0
    ramp_rate:    float = 10.0    # %/s
    default:      float = 100.0
    warning_low:  float = 20.0


VALVE_CONFIGS: dict[str, ValveConfig] = {
    "v1": ValveConfig(
        name        = "V1 — Admission HP (80% débit)",
        min_opening = 0.0,
        max_opening = 100.0,
        ramp_rate   = 5.0,     # ouverture lente (chocs thermiques)
        default     = 100.0,
        warning_low = 30.0,
    ),
    "v2": ValveConfig(
        name        = "V2 — Équilibrage mécanique",
        min_opening = 0.0,
        max_opening = 100.0,
        ramp_rate   = 15.0,
        default     = 100.0,
        warning_low = 10.0,
    ),
    "v3": ValveConfig(
        name        = "V3 — Équilibrage mécanique",
        min_opening = 0.0,
        max_opening = 100.0,
        ramp_rate   = 15.0,
        default     = 100.0,
        warning_low = 10.0,
    ),
    "mp": ValveConfig(
        name        = "Vanne MP — Extraction vers barillet",
        min_opening = 0.0,
        max_opening = 100.0,
        ramp_rate   = 10.0,
        default     = 50.0,    # nominale ~50%
        warning_low = 5.0,
    ),
    "bp": ValveConfig(
        name        = "Vanne BP — Sortie vers condenseur",
        min_opening = 5.0,     # ne doit jamais être totalement fermée
        max_opening = 100.0,
        ramp_rate   = 15.0,
        default     = 80.0,    # nominale ~80%
        warning_low = 10.0,
    ),
}


@dataclass
class ValveState:
    current:  float
    target:   float
    config:   ValveConfig
    _last_update: float = field(default_factory=time.time, repr=False)

    def step(self, dt: float) -> bool:
        if abs(self.current - self.target) < 0.05:
            self.current = self.target
            return True
        max_delta = self.config.ramp_rate * dt
        delta     = self.target - self.current
        if abs(delta) <= max_delta:
            self.current = self.target
        else:
            self.current += max_delta * (1 if delta > 0 else -1)
        self.current = max(self.config.min_opening,
                           min(self.config.max_opening, self.current))
        self._last_update = time.time()
        return False

    @property
    def is_moving(self) -> bool:
        return abs(self.current - self.target) >= 0.05

    @property
    def status(self) -> str:
        if self.is_moving:
            return "MOVING"
        if self.current >= 95.0:
            return "OPEN"
        if self.current <= self.config.min_opening + 1.0:
            return "CLOSED"
        return "PARTIAL"


class ValveController:
    """Gestionnaire des 5 vannes du GTA en régime permanent."""

    def __init__(self):
        self._valves: dict[str, ValveState] = {
            key: ValveState(current=cfg.default, target=cfg.default, config=cfg)
            for key, cfg in VALVE_CONFIGS.items()
        }
        self._current_power_mw: float = 0.0   # mise à jour par FakeAPI

    def update_power(self, active_power_mw: float):
        """Informe le contrôleur de la puissance actuelle (pour les règles de sécurité)."""
        self._current_power_mw = active_power_mw

    def set_valve(self, valve_id: str, target_pct: float) -> dict:
        """Commande une vanne avec vérification des règles de sécurité."""
        valve_id = valve_id.lower()
        if valve_id not in self._valves:
            return {"accepted": False, "message": f"Vanne '{valve_id}' inconnue"}

        valve  = self._valves[valve_id]
        config = valve.config

        clamped = max(config.min_opening, min(config.max_opening, target_pct))

        # ── Règle 1 : valve_bp ≥ 5% si V1 > 10% ──
        if valve_id == "bp" and clamped < 5.0:
            if self._valves["v1"].current > 10.0:
                return {
                    "accepted": False,
                    "message":  "Sécurité : valve BP ne peut pas fermer si V1 > 10%. Fermez d'abord V1.",
                }

        # ── Règle 2 : valve_mp < 80% si puissance > 22 MW ──
        if valve_id == "mp" and clamped > 80.0 and self._current_power_mw > 22.0:
            return {
                "accepted": False,
                "message":  (
                    f"Sécurité : valve MP limitée à 80% si puissance > 22 MW "
                    f"(actuelle {self._current_power_mw:.1f} MW). "
                    "Risque surpression barillet BP."
                ),
            }

        # ── Alerte : fermeture rapide V1 ──
        if valve_id == "v1" and clamped < 20.0 and valve.current > 60.0:
            logger.warning("[ValveCtrl] Fermeture rapide V1 — risque choc thermique")

        valve.target = clamped
        logger.info(f"[ValveCtrl] {config.name} → cible {clamped:.1f}%")
        return {
            "accepted": True,
            "message":  f"{config.name} : déplacement vers {clamped:.1f}%",
            "target":   clamped,
        }

    def set_all(self, v1: Optional[float] = None, v2: Optional[float] = None,
                v3: Optional[float] = None, valve_mp: Optional[float] = None,
                valve_bp: Optional[float] = None) -> dict:
        results = {}
        for key, val in [("v1", v1), ("v2", v2), ("v3", v3),
                         ("mp", valve_mp), ("bp", valve_bp)]:
            if val is not None:
                results[key] = self.set_valve(key, val)
        return results

    def reset_to_nominal(self):
        for key, valve in self._valves.items():
            valve.target = valve.config.default
        logger.info("[ValveCtrl] Réinitialisation nominale")

    def emergency_close(self):
        """Fermeture d'urgence V1 (coupe admission vapeur HP)."""
        self._valves["v1"].current = 0.0
        self._valves["v1"].target  = 0.0
        logger.critical("[ValveCtrl] FERMETURE D'URGENCE V1 !")

    def update(self, dt: float = 0.5):
        for valve in self._valves.values():
            valve.step(dt)

    def get_positions(self) -> dict[str, float]:
        return {key: round(v.current, 2) for key, v in self._valves.items()}

    def get_state(self) -> dict:
        return {
            key: {
                "name":     v.config.name,
                "current":  round(v.current, 2),
                "target":   round(v.target, 2),
                "status":   v.status,
                "is_moving": v.is_moving,
            }
            for key, v in self._valves.items()
        }

    def get_warnings(self) -> list[str]:
        warnings = []
        for key, valve in self._valves.items():
            if valve.current < valve.config.warning_low and valve.status != "CLOSED":
                warnings.append(f"{valve.config.name} : position faible ({valve.current:.1f}%)")
        return warnings

    @property
    def v1(self) -> float: return self._valves["v1"].current
    @property
    def v2(self) -> float: return self._valves["v2"].current
    @property
    def v3(self) -> float: return self._valves["v3"].current
    @property
    def valve_mp(self) -> float: return self._valves["mp"].current
    @property
    def valve_bp(self) -> float: return self._valves["bp"].current


valve_controller = ValveController()