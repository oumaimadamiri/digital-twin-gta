"""
simulation/degradation.py — Modèle de dégradation Weibull du GTA

Comptabilise les heures en régime GRID_CONNECTED et calcule les dérives
progressives appliquées sur le snapshot simulé (rendement, vibrations, paliers).

CDF Weibull : F(t) = 1 - exp(-(t/λ)^k)
  k=2.5 → usure accélérée (défaut de lubrification typique GTA)
  λ=8000h → vie caractéristique
"""

import math
import time
import logging
from typing import Optional

from core.config import (
    DEGRADATION_ENABLED,
    DEGRADATION_SHAPE,
    DEGRADATION_SCALE_H,
    DEGRADATION_MAX_EFF_DRIFT_PCT,
    DEGRADATION_MAX_VIB_DRIFT_MMS,
    DEGRADATION_MAX_BEARING_DRIFT_C,
    DEGRADATION_PERSIST_INTERVAL_S,
)

logger = logging.getLogger("gta.degradation")


class DegradationModel:
    """Suit l'usure cumulée du GTA et expose les dérives Weibull."""

    def __init__(self):
        self.grid_hours: float = 0.0
        self._t_last_persist: float = time.time()
        self._load_from_db()

    def _load_from_db(self) -> None:
        """Restaure le compteur depuis SQLite au démarrage (import différé)."""
        try:
            from services.data_manager import data_manager
            stored = data_manager.get_kv("degradation.grid_hours")
            if stored is not None:
                self.grid_hours = float(stored)
                logger.info("[Dégradation] Restauré %.2f h GRID depuis SQLite", self.grid_hours)
        except Exception as exc:
            logger.warning("[Dégradation] Impossible de restaurer depuis SQLite : %s", exc)

    def _cdf(self) -> float:
        """CDF Weibull au point courant d'heures GRID."""
        if self.grid_hours <= 0:
            return 0.0
        return 1.0 - math.exp(-(self.grid_hours / DEGRADATION_SCALE_H) ** DEGRADATION_SHAPE)

    def update(self, dt: float, is_grid_connected: bool) -> dict:
        """
        Avance le compteur d'un tick dt (secondes) et retourne les dérives.

        Retour :
          eff_drift_pct        : dérive rendement (négatif, %)
          vib_drift_mms        : dérive vibration (positif, mm/s)
          bearing_temp_drift_c : dérive température paliers (positif, °C)
          grid_hours           : heures cumulées GRID
          wear_cdf             : CDF Weibull [0, 1]
        """
        if is_grid_connected:
            self.grid_hours += dt / 3600.0

        cdf = self._cdf()

        # Persistance périodique (import différé pour éviter cycle d'import)
        now = time.time()
        if now - self._t_last_persist >= DEGRADATION_PERSIST_INTERVAL_S:
            self._persist()
            self._t_last_persist = now

        return {
            "eff_drift_pct":        round(DEGRADATION_MAX_EFF_DRIFT_PCT  * cdf, 4),
            "vib_drift_mms":        round(DEGRADATION_MAX_VIB_DRIFT_MMS  * cdf, 4),
            "bearing_temp_drift_c": round(DEGRADATION_MAX_BEARING_DRIFT_C * cdf, 4),
            "grid_hours":           round(self.grid_hours, 3),
            "wear_cdf":             round(cdf, 5),
        }

    def _persist(self) -> None:
        try:
            from services.data_manager import data_manager
            data_manager.set_kv("degradation.grid_hours", f"{self.grid_hours:.4f}")
        except Exception as exc:
            logger.warning("[Dégradation] Persistance échouée : %s", exc)

    def reset(self, operator: str = "Opérateur") -> dict:
        """Remet le compteur à zéro (test / maintenance)."""
        before = self.grid_hours
        self.grid_hours = 0.0
        self._persist()
        try:
            from services.data_manager import data_manager
            data_manager.log_operator_action(
                user=operator,
                action_type="DEGRADATION_RESET",
                value_before=str(round(before, 3)),
                value_after="0.0",
            )
        except Exception:
            pass
        logger.info("[Dégradation] Reset par %s (était %.2f h)", operator, before)
        return {"accepted": True, "grid_hours_before": round(before, 3), "grid_hours": 0.0}

    def snapshot(self) -> dict:
        """État courant pour exposition API."""
        cdf = self._cdf()
        return {
            "grid_hours": round(self.grid_hours, 3),
            "wear_cdf":   round(cdf, 5),
            "eff_drift_pct":        round(DEGRADATION_MAX_EFF_DRIFT_PCT  * cdf, 4),
            "vib_drift_mms":        round(DEGRADATION_MAX_VIB_DRIFT_MMS  * cdf, 4),
            "bearing_temp_drift_c": round(DEGRADATION_MAX_BEARING_DRIFT_C * cdf, 4),
        }


# Singleton
degradation = DegradationModel()
