"""
api/routes_settings.py — Endpoints configuration et alertes
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.alert_manager import alert_manager
from services.data_manager import data_manager

router = APIRouter(prefix="/settings", tags=["Configuration"])


class ThresholdUpdate(BaseModel):
    thresholds: dict   # {param_name: {min: float, max: float}}


@router.get("/thresholds")
def get_thresholds():
    """Retourne les seuils d'alarme actuels."""
    return alert_manager.get_thresholds()


@router.put("/thresholds")
def update_thresholds(body: ThresholdUpdate):
    """Met à jour les seuils d'alarme à chaud."""
    alert_manager.update_thresholds(body.thresholds)
    return {"status": "updated", "thresholds": alert_manager.get_thresholds()}


@router.get("/alerts")
def get_all_alerts(limit: int = 100, only_active: bool = False):
    """Retourne toutes les alertes (seuils + IA)."""
    return data_manager.get_alerts(limit=limit, only_active=only_active)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int):
    """Acquitte une alerte par son ID."""
    data_manager.acknowledge_alert(alert_id)
    alert_manager.clear_alerts()
    return {"status": "acknowledged", "alert_id": alert_id}