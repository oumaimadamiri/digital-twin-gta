"""
ai/lstm_predictor.py — Prédiction des séries temporelles (LSTM)
Prédit l'évolution future des paramètres GTA sur un horizon configurable.
"""

import numpy as np
import os
from collections import deque
from core.config import LSTM_PATH, LSTM_SEQUENCE_LENGTH, LSTM_HORIZON, NOMINAL


class LSTMPredictor:
    """
    Prédicteur LSTM pour les séries temporelles.
    Implémentation avec fallback statistique (régression linéaire)
    si TensorFlow n'est pas installé.
    """

    FEATURES = ["pressure_hp", "temperature_hp", "active_power",
                 "turbine_speed", "power_factor"]

    def __init__(self):
        self.seq_length = LSTM_SEQUENCE_LENGTH
        self.horizon    = LSTM_HORIZON
        self._buffer    = deque(maxlen=self.seq_length)
        self._model     = None
        self._load()

    def _load(self):
        """Essaie de charger le modèle Keras, sinon mode statistique."""
        if os.path.exists(LSTM_PATH):
            try:
                from tensorflow.keras.models import load_model
                self._model = load_model(LSTM_PATH)
            except Exception:
                self._model = None

    def push(self, params: dict):
        """Ajoute un snapshot au buffer glissant."""
        self._buffer.append(self._extract(params))

    def predict(self, params: dict = None) -> dict:
        """
        Prédit l'évolution sur `horizon` pas de 500ms.
        Retourne les valeurs prédites et l'intervalle de confiance.
        """
        if params:
            self.push(params)

        if len(self._buffer) < 3:
            return {"ready": False, "message": "Buffer insuffisant (< 3 points)"}

        data = np.array(list(self._buffer))   # (seq_len, n_features)

        if self._model is not None:
            predictions = self._predict_lstm(data)
        else:
            predictions = self._predict_linear(data)

        # Intervalles de confiance ±2% (simplifié)
        confidence = predictions * 0.02

        return {
            "ready":              True,
            "features":           self.FEATURES,
            "predicted_values":   predictions.tolist(),
            "confidence_lower":   (predictions - confidence).tolist(),
            "confidence_upper":   (predictions + confidence).tolist(),
            "horizon_steps":      self.horizon,
            "horizon_seconds":    self.horizon * 0.5,
        }

    def _predict_linear(self, data: np.ndarray) -> np.ndarray:
        """
        Régression linéaire par feature : extrapolation simple
        (remplacé par le vrai LSTM en production).
        """
        n = data.shape[0]
        x = np.arange(n)
        predictions = np.zeros((self.horizon, data.shape[1]))

        for i in range(data.shape[1]):
            y     = data[:, i]
            coef  = np.polyfit(x, y, 1)          # pente + intercept
            x_fut = np.arange(n, n + self.horizon)
            pred  = np.polyval(coef, x_fut)
            # Clamping autour du nominal ±20%
            nom = list(NOMINAL.values())[i] if i < len(NOMINAL) else pred[0]
            predictions[:, i] = np.clip(pred, nom * 0.80, nom * 1.20)

        return predictions

    def _predict_lstm(self, data: np.ndarray) -> np.ndarray:
        """Prédiction avec le vrai modèle LSTM Keras."""
        x    = data[-self.seq_length:][np.newaxis, ...]   # (1, seq_len, features)
        pred = self._model.predict(x, verbose=0)           # (1, horizon, features)
        return pred[0]

    def _extract(self, params: dict) -> np.ndarray:
        return np.array([params.get(f, 0.0) for f in self.FEATURES], dtype=float)


lstm_predictor = LSTMPredictor()