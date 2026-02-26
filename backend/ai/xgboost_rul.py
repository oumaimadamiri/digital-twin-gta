"""
ai/xgboost_rul.py — Estimation du Remaining Useful Life (RUL) via XGBoost
Estime le nombre de jours avant qu'un paramètre critique franchisse un seuil.
"""

import numpy as np
import os
import pickle
from datetime import datetime, timedelta
from core.config import XGBOOST_PATH, THRESHOLDS, NOMINAL


class XGBoostRUL:
    """
    Estimateur RUL basé sur XGBoost (ou régression de repli).
    Calcule les features de dégradation à partir de l'historique récent.
    """

    def __init__(self):
        self._model = None
        self._load()

    def _load(self):
        if os.path.exists(XGBOOST_PATH):
            try:
                with open(XGBOOST_PATH, "rb") as f:
                    self._model = pickle.load(f)
            except Exception:
                self._model = None

    def estimate_rul(self, history: list[dict]) -> dict:
        """
        Estime le RUL à partir des derniers snapshots.
        history : liste de dicts (paramètres GTA triés par timestamp ASC).
        """
        if len(history) < 5:
            return {"ready": False, "message": "Historique insuffisant (< 5 points)"}

        features = self._compute_features(history)

        if self._model is not None:
            rul_days = float(self._model.predict([features])[0])
        else:
            rul_days = self._estimate_statistical(history, features)

        rul_days = max(0.0, round(rul_days, 1))
        failure_date = datetime.utcnow() + timedelta(days=rul_days)

        return {
            "ready":                True,
            "rul_days":             rul_days,
            "estimated_failure":    failure_date.strftime("%d/%m/%Y"),
            "confidence":           0.80,
            "degradation_score":    round(features.get("degradation_index", 0), 3),
            "critical_parameter":   features.get("worst_param", "N/A"),
        }

    def _compute_features(self, history: list[dict]) -> dict:
        """
        Calcule les features de dégradation :
        - Écart moyen au nominal pour chaque paramètre
        - Tendance (pente) sur la fenêtre
        - Index de dégradation global
        """
        params_tracked = [
            "pressure_hp", "temperature_hp", "active_power",
            "turbine_speed", "efficiency", "power_factor"
        ]
        features     = {}
        worst_dev    = 0.0
        worst_param  = "N/A"

        for p in params_tracked:
            values    = [h.get(p, NOMINAL.get(p, 0)) for h in history if h.get(p)]
            if not values:
                continue
            nom       = NOMINAL.get(p, 1.0)
            # Déviation normalisée
            deviation = abs(np.mean(values) - nom) / (abs(nom) + 1e-9)
            features[f"{p}_deviation"] = deviation
            # Tendance (pente normalisée)
            if len(values) > 2:
                x = np.arange(len(values))
                slope = np.polyfit(x, values, 1)[0]
                features[f"{p}_slope"] = slope / (abs(nom) + 1e-9)
            else:
                features[f"{p}_slope"] = 0.0

            if deviation > worst_dev:
                worst_dev   = deviation
                worst_param = p

        # Index de dégradation global (0 = nominal, 1 = critique)
        devs = [v for k, v in features.items() if k.endswith("_deviation")]
        features["degradation_index"] = float(np.mean(devs)) if devs else 0.0
        features["worst_param"]       = worst_param
        return features

    def _estimate_statistical(self, history: list[dict], features: dict) -> float:
        """
        Estimation statistique simple du RUL quand XGBoost n'est pas disponible.
        RUL = 30 × (1 - degradation_index)  → de 0 à 30 jours.
        """
        deg = features.get("degradation_index", 0.0)
        rul = 30.0 * (1.0 - min(deg * 5, 1.0))   # dégradation amplifiée × 5
        return max(0.5, rul)

    def train(self, X: list[dict], y: list[float]):
        """Entraîne le modèle XGBoost (appelé depuis train_models.py)."""
        try:
            import xgboost as xgb
            features_list = [list(self._compute_features([row]).values()) for row in X]
            self._model   = xgb.XGBRegressor(n_estimators=100, max_depth=4)
            self._model.fit(features_list, y)
            os.makedirs(os.path.dirname(XGBOOST_PATH), exist_ok=True)
            with open(XGBOOST_PATH, "wb") as f:
                pickle.dump(self._model, f)
        except ImportError:
            print("[XGBoost] xgboost non installé, entraînement ignoré.")


xgboost_rul = XGBoostRUL()