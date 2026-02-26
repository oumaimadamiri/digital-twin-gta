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
    En l'absence de TensorFlow, fonctionne avec un modèle statistique simplifié
    (distance de Mahalanobis) qui peut être remplacé par un vrai réseau de neurones.
    """

    FEATURES = [
        "pressure_hp", "temperature_hp", "steam_flow_hp",
        "turbine_speed", "active_power", "power_factor", "efficiency"
    ]

    def __init__(self):
        self.threshold      = AUTOENCODER_THRESHOLD
        self._is_trained    = False
        self._mean: np.ndarray  = None
        self._std:  np.ndarray  = None
        # Chargement si modèle existant
        self._load()

    def _load(self):
        """Charge les paramètres du modèle depuis le disque."""
        stats_path = AUTOENCODER_PATH.replace(".h5", "_stats.npz")
        if os.path.exists(stats_path):
            data = np.load(stats_path)
            self._mean       = data["mean"]
            self._std        = data["std"]
            self._is_trained = True

    def train(self, data: list[dict]):
        """Entraîne le modèle sur des données nominales (liste de dicts)."""
        X = self._to_matrix(data)
        self._mean       = X.mean(axis=0)
        # Évite des écarts-types quasi nuls qui exploseraient la distance
        raw_std          = X.std(axis=0)
        min_std          = np.abs(self._mean) * 0.01  # au moins 1% de la valeur nominale
        self._std        = np.maximum(raw_std, min_std) + 1e-8
        self._is_trained = True
        # Sauvegarde
        os.makedirs(os.path.dirname(AUTOENCODER_PATH), exist_ok=True)
        stats_path = AUTOENCODER_PATH.replace(".h5", "_stats.npz")
        np.savez(stats_path, mean=self._mean, std=self._std)

    def reconstruction_error(self, params: dict) -> float:
        """
        Calcule l'erreur de reconstruction (distance normalisée au nominal).
        En production, remplacer par la vraie erreur de reconstruction du réseau.
        """
        if not self._is_trained:
            return 0.0
        x      = self._extract_features(params)
        z      = (x - self._mean) / self._std
        error  = float(np.sqrt(np.mean(z ** 2)))
        return round(error, 4)

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