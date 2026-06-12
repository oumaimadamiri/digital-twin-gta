"""
ai/__init__.py — Orchestrateur des modèles IA
Expose:
- la classe AIModule (orchestrateur)
- l'instance globale ai_module utilisée par l'API FastAPI.
"""

from typing import List, Dict, Any

from .autoencoder import autoencoder
from .lstm_predictor import lstm_predictor
from .xgboost_rul import xgboost_rul


class AIModule:
    """
    Orchestrateur des différents modèles IA.

    - Autoencodeur : détection d'anomalies sur le snapshot courant
    - LSTM : prédiction de l'évolution des paramètres
    - XGBoost/statistique : estimation du Remaining Useful Life (RUL)
    """

    def __init__(self):
        self._autoencoder = autoencoder
        self._lstm        = lstm_predictor
        self._rul         = xgboost_rul

    # ─────────────────────────────────────────────
    # ANALYSES ATOMIQUES
    # ─────────────────────────────────────────────

    def run_detection(self, current_params: Dict[str, Any]) -> Dict[str, Any]:
        """Détection d'anomalie sur un snapshot courant."""
        return self._autoencoder.predict(current_params)

    def run_prediction(self, current_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prédiction de l'évolution future à partir du snapshot courant.
        Le LSTM maintient en interne un buffer glissant des derniers snapshots.
        """
        return self._lstm.predict(current_params)

    def estimate_rul(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Estimation du Remaining Useful Life (RUL) à partir de l'historique."""
        return self._rul.estimate_rul(history)

    # ─────────────────────────────────────────────
    # ANALYSE COMPLÈTE
    # ─────────────────────────────────────────────

    def run_full_analysis(
        self,
        current_params: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Exécute l'analyse complète :
        - détection d'anomalie (autoencodeur)
        - prédiction LSTM
        - estimation RUL
        """
        anomaly     = self.run_detection(current_params)
        prediction  = self.run_prediction(current_params)
        rul_result  = self.estimate_rul(history)

        return {
            "anomaly_detection": anomaly,
            "lstm_prediction":   prediction,
            "rul_estimation":    rul_result,
        }
    def run_anomaly_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Recalcule l'erreur de reconstruction AE sur les derniers snapshots
        de l'historique réel (ordre chronologique, le plus récent en dernier).
        """
        recent = list(reversed(history[:20]))
        errors = self._autoencoder.reconstruction_errors_batch(recent)
        return [
            {"timestamp": h.get("timestamp"), "reconstruction_error": e}
            for h, e in zip(recent, errors)
        ]
    
    def get_last_training_date(self) -> str:
        """Date du dernier (ré)entraînement de l'autoencodeur (mtime des stats sauvegardées)."""
        import os
        from datetime import datetime
        from core.config import AUTOENCODER_PATH

        stats_path = AUTOENCODER_PATH.replace(".h5", "_stats.npz")
        if os.path.exists(stats_path):
            ts = os.path.getmtime(stats_path)
            return datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")
        return "N/A"

# Instance globale utilisée par les routes FastAPI
ai_module = AIModule()
