"""
simulation/valve_controller.py — Logique de contrôle des vannes V1, V2, V3
Gère les règles de sécurité, les rampes d'ouverture/fermeture et les
interdépendances entre les vannes du GTA.

  V1 — Vanne d'admission vapeur HP  (amont turbine)
  V2 — Vanne d'extraction intermédiaire MP (entre étages HP et BP)
  V3 — Vanne de sortie vapeur BP   (vers condenseur / cogénération)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("gta.valves")


# ─────────────────────────────────────────────
# CONFIGURATION DES VANNES
# ─────────────────────────────────────────────

@dataclass
class ValveConfig:
    """Paramètres physiques et limites d'une vanne."""
    name:           str
    min_opening:    float = 0.0          # % ouverture minimale autorisée
    max_opening:    float = 100.0        # % ouverture maximale autorisée
    ramp_rate:      float = 10.0         # %/s — vitesse max de variation
    default:        float = 100.0        # % — position nominale
    # Seuils d'alarme
    warning_low:    float = 20.0         # % — alerte si en dessous
    warning_high:   float = 95.0         # % — alerte si au-dessus (pour V2/V3)


VALVE_CONFIGS: dict[str, ValveConfig] = {
    "v1": ValveConfig(
        name         = "V1 — Admission HP",
        min_opening  = 0.0,
        max_opening  = 100.0,
        ramp_rate    = 5.0,      # ouverture lente pour éviter les chocs thermiques
        default      = 100.0,
        warning_low  = 30.0,
    ),
    "v2": ValveConfig(
        name         = "V2 — Extraction MP",
        min_opening  = 0.0,
        max_opening  = 100.0,
        ramp_rate    = 15.0,
        default      = 100.0,
        warning_low  = 10.0,
    ),
    "v3": ValveConfig(
        name         = "V3 — Sortie BP",
        min_opening  = 5.0,      # ne doit jamais être totalement fermée (sécurité)
        max_opening  = 100.0,
        ramp_rate    = 15.0,
        default      = 100.0,
        warning_low  = 10.0,
    ),
}


# ─────────────────────────────────────────────
# ÉTAT D'UNE VANNE
# ─────────────────────────────────────────────

@dataclass
class ValveState:
    """État courant d'une vanne (position + rampe en cours)."""
    current:    float        # % position actuelle
    target:     float        # % position cible (pour rampe)
    config:     ValveConfig
    _last_update: float = field(default_factory=time.time, repr=False)

    def step(self, dt: float) -> bool:
        """
        Avance la rampe d'ouverture/fermeture sur un pas de temps dt (secondes).
        Retourne True si la position cible est atteinte.
        """
        if abs(self.current - self.target) < 0.05:
            self.current = self.target
            return True

        max_delta = self.config.ramp_rate * dt
        delta     = self.target - self.current

        if abs(delta) <= max_delta:
            self.current = self.target
        else:
            self.current += max_delta * (1 if delta > 0 else -1)

        # Contraindre dans les limites physiques
        self.current = max(self.config.min_opening,
                           min(self.config.max_opening, self.current))
        self._last_update = time.time()
        return False

    @property
    def is_moving(self) -> bool:
        return abs(self.current - self.target) >= 0.05

    @property
    def status(self) -> str:
        """Retourne le statut de la vanne : OPEN / PARTIAL / CLOSED / MOVING."""
        if self.is_moving:
            return "MOVING"
        if self.current >= 95.0:
            return "OPEN"
        if self.current <= self.config.min_opening + 1.0:
            return "CLOSED"
        return "PARTIAL"


# ─────────────────────────────────────────────
# CONTRÔLEUR PRINCIPAL
# ─────────────────────────────────────────────

class ValveController:
    """
    Gestionnaire des 3 vannes du GTA.

    Responsabilités :
      - Appliquer les commandes opérateur avec contraintes physiques
      - Gérer les rampes d'ouverture/fermeture
      - Vérifier les interdépendances (ex : V3 ne peut pas être fermée si V1 ouverte)
      - Fournir les positions courantes au FakeAPI
    """

    def __init__(self):
        self._valves: dict[str, ValveState] = {
            key: ValveState(
                current = cfg.default,
                target  = cfg.default,
                config  = cfg,
            )
            for key, cfg in VALVE_CONFIGS.items()
        }

    # ──────────────────────────────────────────
    # COMMANDES
    # ──────────────────────────────────────────

    def set_valve(self, valve_id: str, target_pct: float) -> dict:
        """
        Commande une vanne vers une position cible (0–100%).
        Applique les règles de sécurité avant d'accepter la commande.
        Retourne un dict {accepted, message, target}.
        """
        valve_id = valve_id.lower()
        if valve_id not in self._valves:
            return {"accepted": False, "message": f"Vanne {valve_id} inconnue"}

        valve  = self._valves[valve_id]
        config = valve.config

        # 1) Contrainte de plage
        clamped = max(config.min_opening, min(config.max_opening, target_pct))
        if clamped != target_pct:
            logger.warning(
                f"[ValveCtrl] {valve_id} : consigne {target_pct:.1f}% "
                f"ramenée à {clamped:.1f}% (limites [{config.min_opening}, {config.max_opening}])"
            )

        # 2) Règle de sécurité : V3 ne peut pas descendre sous 5% si V1 > 10%
        if valve_id == "v3" and clamped < 5.0:
            v1_pos = self._valves["v1"].current
            if v1_pos > 10.0:
                return {
                    "accepted": False,
                    "message":  "Sécurité : V3 ne peut pas fermer si V1 est ouverte (>10%). "
                                "Fermez d'abord V1.",
                }

        # 3) Alerte si V1 fermée brusquement
        if valve_id == "v1" and clamped < 20.0 and valve.current > 60.0:
            logger.warning("[ValveCtrl] Fermeture rapide de V1 détectée — choc thermique possible")

        valve.target = clamped
        logger.info(f"[ValveCtrl] {config.name} → cible {clamped:.1f}%")
        return {
            "accepted": True,
            "message":  f"{config.name} : déplacement vers {clamped:.1f}%",
            "target":   clamped,
        }

    def set_all(self, v1: Optional[float] = None,
                v2: Optional[float] = None,
                v3: Optional[float] = None) -> dict:
        """Commande simultanée des 3 vannes."""
        results = {}
        if v1 is not None:
            results["v1"] = self.set_valve("v1", v1)
        if v2 is not None:
            results["v2"] = self.set_valve("v2", v2)
        if v3 is not None:
            results["v3"] = self.set_valve("v3", v3)
        return results

    def reset_to_nominal(self):
        """Ramène toutes les vannes à leur position nominale."""
        for key, valve in self._valves.items():
            valve.target = valve.config.default
        logger.info("[ValveCtrl] Réinitialisation nominale demandée")

    def emergency_close(self):
        """Fermeture d'urgence de V1 uniquement (coupe l'admission vapeur)."""
        self._valves["v1"].current = 0.0
        self._valves["v1"].target  = 0.0
        logger.critical("[ValveCtrl] FERMETURE D'URGENCE V1 déclenchée !")

    # ──────────────────────────────────────────
    # MISE À JOUR (appelée par FakeAPI à chaque tick)
    # ──────────────────────────────────────────

    def update(self, dt: float = 0.5):
        """Avance les rampes de toutes les vannes sur un pas dt (secondes)."""
        for valve in self._valves.values():
            valve.step(dt)

    # ──────────────────────────────────────────
    # LECTURE
    # ──────────────────────────────────────────

    def get_positions(self) -> dict[str, float]:
        """Retourne les positions courantes (utilisé par FakeAPI)."""
        return {key: round(v.current, 2) for key, v in self._valves.items()}

    def get_state(self) -> dict:
        """Retourne l'état détaillé de toutes les vannes."""
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
        """Retourne les avertissements de position anormale."""
        warnings = []
        for key, valve in self._valves.items():
            if valve.current < valve.config.warning_low and valve.status != "CLOSED":
                warnings.append(
                    f"{valve.config.name} : position faible ({valve.current:.1f}%)"
                )
        return warnings

    # ──────────────────────────────────────────
    # PROPRIÉTÉS RAPIDES
    # ──────────────────────────────────────────

    @property
    def v1(self) -> float:
        return self._valves["v1"].current

    @property
    def v2(self) -> float:
        return self._valves["v2"].current

    @property
    def v3(self) -> float:
        return self._valves["v3"].current


# Instance globale partagée avec FakeAPI
valve_controller = ValveController()