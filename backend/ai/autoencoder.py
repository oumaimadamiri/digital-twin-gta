"""
ai/autoencoder.py — Détection d'anomalies par autoencodeur
Entraîné sur données nominales, détecte les déviations via erreur de reconstruction.
"""

import numpy as np
import os
from core.config import AUTOENCODER_PATH, AUTOENCODER_THRESHOLD


class Autoencoder:
    """
    Autoencodeur pour la détection d'anomalies non supervisée.
    Réseau Keras dense (7→4→2→4→7) entraîné sur données nominales normalisées.
    Fallback : distance de Mahalanobis simplifiée si TensorFlow/modèle indisponible.
    """

    FEATURES = [
        "pressure_hp", "temperature_hp", "steam_flow_hp",
        "turbine_speed", "active_power", "power_factor", "efficiency"
    ]

    def __init__(self):
        self.threshold      = AUTOENCODER_THRESHOLD
        self._is_trained    = False
        self._model         = None
        self._mean: np.ndarray  = None
        self._std:  np.ndarray  = None
        self._load()

    def _stats_path(self) -> str:
        return AUTOENCODER_PATH.replace(".h5", "_stats.npz")

    def _load(self):
        """Charge les paramètres de normalisation/seuil et, si possible, le modèle Keras."""
        stats_path = self._stats_path()
        if os.path.exists(stats_path):
            data = np.load(stats_path)
            self._mean       = data["mean"]
            self._std        = data["std"]
            if "threshold" in data:
                self.threshold = float(data["threshold"])
            self._is_trained = True

        if os.path.exists(AUTOENCODER_PATH):
            try:
                from tensorflow.keras.models import load_model
                self._model = load_model(AUTOENCODER_PATH)
            except Exception:
                self._model = None

    def train(self, data: list[dict]):
        """Entraîne le modèle sur des données nominales (liste de dicts)."""
        X = self._to_matrix(data)

        # Normalisation (utilisée par le réseau ET par le fallback Mahalanobis)
        self._mean       = X.mean(axis=0)
        raw_std          = X.std(axis=0)
        min_std          = np.abs(self._mean) * 0.01  # au moins 1% de la valeur nominale
        self._std        = np.maximum(raw_std, min_std) + 1e-8
        self._is_trained = True

        os.makedirs(os.path.dirname(AUTOENCODER_PATH), exist_ok=True)
        np.savez(self._stats_path(), mean=self._mean, std=self._std, threshold=self.threshold)

        X_norm = (X - self._mean) / self._std

        try:
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Dense
            from tensorflow.keras.callbacks import EarlyStopping

            n_features = X_norm.shape[1]
            model = Sequential([
                Dense(4, activation="relu", input_shape=(n_features,)),
                Dense(2, activation="relu"),
                Dense(4, activation="relu"),
                Dense(n_features, activation="linear"),
            ])
            model.compile(optimizer="adam", loss="mse")
            model.fit(
                X_norm, X_norm,
                epochs=50, batch_size=32,
                validation_split=0.15,
                callbacks=[EarlyStopping(patience=5, restore_best_weights=True)],
                verbose=0,
            )
            model.save(AUTOENCODER_PATH)
            self._model = model
        except ImportError:
            self._model = None  # TensorFlow absent → fallback Mahalanobis actif

    def set_threshold(self, threshold: float):
        """Met à jour le seuil de détection et le persiste avec les stats de normalisation."""
        self.threshold = threshold
        np.savez(self._stats_path(), mean=self._mean, std=self._std, threshold=threshold)

    def reconstruction_error(self, params: dict) -> float:
        """
        Calcule l'erreur de reconstruction.
        - Si modèle Keras chargé : MSE entre l'entrée normalisée et sa reconstruction.
        - Sinon : distance de Mahalanobis simplifiée (fallback).
        """
        if not self._is_trained:
            return 0.0

        x = self._extract_features(params)
        z = (x - self._mean) / self._std

        if self._model is not None:
            recon = self._model(z[np.newaxis, :], training=False).numpy()[0]
            error = float(np.mean((z - recon) ** 2))
        else:
            error = float(np.sqrt(np.mean(z ** 2)))

        return round(error, 6)

    def reconstruction_errors_batch(self, params_list: list[dict]) -> list[float]:
        """Calcule l'erreur de reconstruction pour plusieurs snapshots en un seul appel modèle."""
        if not self._is_trained or not params_list:
            return [0.0] * len(params_list)

        X = self._to_matrix(params_list)
        Z = (X - self._mean) / self._std

        if self._model is not None:
            recon  = self._model(Z, training=False).numpy()
            errors = np.mean((Z - recon) ** 2, axis=1)
        else:
            errors = np.sqrt(np.mean(Z ** 2, axis=1))

        return [round(float(e), 6) for e in errors]

    def predict(self, params: dict) -> dict:
        """Retourne le résultat de détection pour un snapshot."""
        error      = self.reconstruction_error(params)
        is_anomaly = error > self.threshold
        score      = min(1.0, error / (self.threshold * 2))
        return {
            "is_anomaly":          is_anomaly,
            "reconstruction_error": error,
            "anomaly_score":        round(score, 3),
            "threshold":            self.threshold,
        }

    def _to_matrix(self, data: list[dict]) -> np.ndarray:
        return np.array([self._extract_features(d) for d in data])

    def _extract_features(self, params: dict) -> np.ndarray:
        from core.config import NOMINAL
        return np.array([
            params.get(f, NOMINAL.get(f, 0)) for f in self.FEATURES
        ], dtype=float)


autoencoder = Autoencoder()