"""
simulation/dynamics.py — Dynamique rotor (inertie turbine-alternateur)

Modèle 1er ordre avec deux régimes :

  GRID_CONNECTED (grid_locked=True) :
    tau_eff = TAU_GRID (~3 s) — raideur réseau
    omega_target_eff = 0.9·omega_nom + 0.1·omega_algébrique
    → vitesse reste très proche de 6435 RPM, légères déviations visibles sur scénarios

  ROLLING / STOPPED (grid_locked=False) :
    tau_eff = TAU = J/D (~12.5 s) — inertie machine seule
    omega_target_eff = omega_algébrique (sortie physics_model)
    → inertie pleine, montée/descente réaliste

Discrétisation ZOH analytique (stable pour tout dt) :
    alpha = exp(-dt / tau_eff)
    omega(k+1) = omega(k)*alpha + omega_target_eff*(1-alpha)

Singleton rotor_dynamics, mis à jour dans fake_api._generate_dual()
après controller.update() et avant la création du snapshot simulé.
"""

import math
import logging

from core.config import NOMINAL, J_INERTIA, D_DAMPING, TAU_GRID

logger = logging.getLogger("gta.dynamics")

OMEGA_NOMINAL = NOMINAL["turbine_speed"] * 2.0 * math.pi / 60.0   # rad/s ~ 673.8
TAU           = J_INERTIA / D_DAMPING                               # ~12.5 s (inertie libre)
GRID_MIX      = 0.10    # part de la vitesse algébrique dans la cible réseau (10%)


class RotorDynamics:
    """Intégrateur de vitesse rotor — singleton."""

    def __init__(self):
        self.omega_rad_s: float = OMEGA_NOMINAL
        self._grid_locked: bool = True

    # ──────────────────────────────────────────────────────
    # PROPRIÉTÉS
    # ──────────────────────────────────────────────────────

    @property
    def speed_rpm(self) -> float:
        return round(self.omega_rad_s * 60.0 / (2.0 * math.pi), 1)

    @property
    def frequency_hz(self) -> float:
        return round(self.speed_rpm / NOMINAL["turbine_speed"] * 50.0, 3)

    @property
    def speed_deviation_rpm(self) -> float:
        """Écart absolu par rapport à la vitesse nominale (RPM)."""
        return abs(self.speed_rpm - NOMINAL["turbine_speed"])

    # ──────────────────────────────────────────────────────
    # TICK — appelé depuis fake_api._generate_dual()
    # ──────────────────────────────────────────────────────

    def update(self, dt: float, target_speed_rpm: float) -> None:
        """
        Intègre la vitesse rotor pour un tick de durée dt (s).
        L'inertie est TOUJOURS active — seule la raideur (tau) change.
        """
        omega_algébrique = target_speed_rpm * 2.0 * math.pi / 60.0

        if self._grid_locked:
            # Réseau couplé : cible = mix 90% nominal + 10% algébrique
            # → vitesse reste proche de 6435 RPM, petites déviations visibles
            omega_target = (1.0 - GRID_MIX) * OMEGA_NOMINAL + GRID_MIX * omega_algébrique
            tau = TAU_GRID
        else:
            # Îloté / arrêt : cible = modèle algébrique complet
            omega_target = omega_algébrique
            tau = TAU

        alpha     = math.exp(-dt / max(tau, 1e-3))
        omega_new = self.omega_rad_s * alpha + omega_target * (1.0 - alpha)

        # Butées physiques : 0 ≤ ω ≤ 115% nominal (survitesse HH)
        self.omega_rad_s = max(0.0, min(OMEGA_NOMINAL * 1.15, omega_new))

    # ──────────────────────────────────────────────────────
    # COMMANDES D'ÉTAT
    # ──────────────────────────────────────────────────────

    def lock_to_grid(self) -> None:
        """Couplage réseau — passe en mode raideur réseau (transition douce)."""
        self._grid_locked = True
        logger.info("[Dynamics] Rotor couplé réseau (TAU_GRID = %.1f s)", TAU_GRID)

    def unlock_from_grid(self) -> None:
        """Découplage réseau — passe en dynamique libre (inertie pleine)."""
        self._grid_locked = False
        logger.info("[Dynamics] Rotor découplé — dynamique libre (TAU = %.1f s)", TAU)

    def reset_to_stop(self) -> None:
        """Arrêt d'urgence — vitesse remise à zéro, dynamique libre."""
        self._grid_locked = False
        self.omega_rad_s  = 0.0
        logger.info("[Dynamics] Rotor à l'arrêt (omega = 0)")

    def snapshot(self) -> dict:
        return {
            "rotor_speed_rpm":   self.speed_rpm,
            "rotor_freq_hz":     self.frequency_hz,
            "rotor_grid_locked": self._grid_locked,
        }


rotor_dynamics = RotorDynamics()
