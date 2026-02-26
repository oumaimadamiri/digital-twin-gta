"""
api/routes_ai.py — Endpoints du module Intelligence Artificielle
"""

from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

from ai import ai_module
from services.data_manager import data_manager
from services.alert_manager import alert_manager

router = APIRouter(prefix="/ai", tags=["Intelligence Artificielle"])


@router.get("/analysis")
def full_analysis():
    """Lance l'analyse complète IA sur les données courantes."""
    current = data_manager.get_from_cache()
    if current is None:
        return {"ready": False, "message": "Pas de données disponibles"}
    history = data_manager.get_history(limit=50)
    result  = ai_module.run_full_analysis(current, history)

    # Si anomalie détectée → créer alerte IA
    anomaly = result.get("anomaly_detection", {})
    if anomaly.get("is_anomaly"):
        alert = alert_manager.add_ai_alert(
            param     = "reconstruction_error",
            value     = anomaly["reconstruction_error"],
            threshold = anomaly["threshold"],
            message   = f"Anomalie détectée (score={anomaly['anomaly_score']:.3f})",
        )
        data_manager.save_alert(alert)

    return result


@router.get("/anomaly")
def detect_anomaly():
    """Détection d'anomalie uniquement (autoencodeur)."""
    current = data_manager.get_from_cache()
    if current is None:
        return {"ready": False}
    return ai_module.run_detection(current)


@router.get("/prediction")
def get_prediction():
    """Prédiction LSTM de l'évolution des paramètres."""
    current = data_manager.get_from_cache()
    if current is None:
        return {"ready": False}
    return ai_module.run_prediction(current)


@router.get("/rul")
def get_rul():
    """Estimation du Remaining Useful Life (XGBoost)."""
    history = data_manager.get_history(limit=100)
    return ai_module.estimate_rul(history)


@router.get("/alerts")
def get_ai_alerts(limit: int = Query(50, ge=1, le=500)):
    """Retourne les alertes IA récentes."""
    alerts = data_manager.get_alerts(limit=limit)
    return [a for a in alerts if a.get("source") == "IA"]