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

        # ── Suivi de précision en continu ──────────────────────────────
        self._last_pred_1step  = None          # prédiction 1-pas faite au tick précédent
        self._precision_history = deque(maxlen=50)

        self._load()

    def _load(self):
        """Charge le modèle Keras + ses stats de normalisation min-max, sinon mode statistique."""
        self._data_min = None
        self._data_max = None

        norm_path = LSTM_PATH.replace(".h5", "_norm.npz")
        if os.path.exists(norm_path):
            stats = np.load(norm_path)
            self._data_min = stats["data_min"]
            self._data_max = stats["data_max"]

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
        Retourne les valeurs prédites, l'intervalle de confiance et la précision mesurée.
        """
        if params:
            self.push(params)

        if len(self._buffer) < 3:
            return {"ready": False, "message": "Buffer insuffisant (< 3 points)"}

        data = np.array(list(self._buffer))   # (seq_len, n_features)

        # ── Évaluation de la prédiction précédente (1 pas) vs réalité ──
        if self._last_pred_1step is not None:
            actual   = data[-1]
            rel_err  = np.abs(actual - self._last_pred_1step) / (np.abs(actual) + 1e-9)
            accuracy = max(0.0, 1.0 - float(np.mean(rel_err)))
            self._precision_history.append(accuracy)

        if self._model is not None and self._data_min is not None:
            predictions = self._predict_lstm(data)
        else:
            predictions = self._predict_linear(data)

        # Mémoriser la prédiction "1 pas en avant" pour évaluation au prochain tick
        self._last_pred_1step = predictions[0]

        precision_pct = (
            round(float(np.mean(self._precision_history)) * 100, 1)
            if self._precision_history else None
        )

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
            "precision_pct":      precision_pct,
        }
    def _predict_linear(self, data: np.ndarray) -> np.ndarray:
        """
        Régression linéaire par feature : extrapolation simple
        (remplacé par le vrai LSTM en production).
        """
        n = data.shape[0]
        x = np.arange(n)
        predictions = np.zeros((self.horizon, data.shape[1]))

        for i, feature in enumerate(self.FEATURES):
            y     = data[:, i]
            coef  = np.polyfit(x, y, 1)          # pente + inter
            x_fut = np.arange(n, n + self.horizon)
            pred  = np.polyval(coef, x_fut)
            # Clamping autour du nominal ±20%
            nom = NOMINAL.get(feature, pred[0])
            predictions[:, i] = np.clip(pred, nom * 0.80, nom * 1.20)

        return predictions

    def _predict_lstm(self, data: np.ndarray) -> np.ndarray:
        """Prédiction avec le modèle LSTM Keras (entrée/sortie normalisées min-max)."""
        data_range = self._data_max - self._data_min + 1e-8
        x_norm = (data[-self.seq_length:] - self._data_min) / data_range
        x      = x_norm[np.newaxis, ...]                  # (1, seq_len, features)

        pred_norm = self._model.predict(x, verbose=0)[0]  # (horizon * features,)
        pred_norm = pred_norm.reshape(self.horizon, len(self.FEATURES))

        return pred_norm * data_range + self._data_min

    def _extract(self, params: dict) -> np.ndarray:
        return np.array([params.get(f, 0.0) for f in self.FEATURES], dtype=float)


lstm_predictor = LSTMPredictor()