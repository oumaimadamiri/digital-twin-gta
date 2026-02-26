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


# Instance globale utilisée par les routes FastAPI
ai_module = AIModule()
