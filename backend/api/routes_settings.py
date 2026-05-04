"""
api/routes_settings.py — Endpoints configuration et alertes
"""
import json as _json

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
def update_thresholds(body: ThresholdUpdate, operator: str = "Opérateur"):
    """Met à jour les seuils d'alarme à chaud."""
    old = alert_manager.get_thresholds()
    alert_manager.update_thresholds(body.thresholds)
    data_manager.log_operator_action(
        user=operator,
        action_type="THRESHOLD_UPDATE",
        target=",".join(body.thresholds.keys()),
        value_before=_json.dumps({k: old.get(k) for k in body.thresholds}),
        value_after=_json.dumps(body.thresholds),
    )
    return {"status": "updated", "thresholds": alert_manager.get_thresholds()}


@router.get("/alerts")
def get_all_alerts(limit: int = 100, only_active: bool = False):
    """Retourne toutes les alertes (seuils + IA)."""
    return data_manager.get_alerts(limit=limit, only_active=only_active)


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, operator: str = "Opérateur"):
    """Acquitte une alerte par son ID (sans effacer les autres alertes actives)."""
    data_manager.acknowledge_alert(alert_id, user=operator)
    data_manager.log_operator_action(
        user=operator,
        action_type="ALERT_ACK",
        target=f"alert_{alert_id}",
        value_before="NON_ACQUITTÉ",
        value_after="ACQUITTÉ",
    )
    return {"status": "acknowledged", "alert_id": alert_id}
