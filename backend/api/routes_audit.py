"""
api/routes_audit.py — Journal opérateur (audit trail)
"""
from fastapi import APIRouter
from fastapi.responses import Response
from datetime import datetime
from typing import Optional

from services.data_manager import data_manager

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/operator-actions")
def get_operator_actions(
    start: Optional[str] = None,
    end:   Optional[str] = None,
    user:  Optional[str] = None,
    limit: int = 200,
):
    """Retourne le journal horodaté des actions opérateur."""
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt   = datetime.fromisoformat(end)   if end   else None
    return data_manager.get_operator_actions(start=start_dt, end=end_dt, user=user, limit=limit)


@router.get("/operator-actions/export/csv")
def export_operator_actions_csv(
    start: Optional[str] = None,
    end:   Optional[str] = None,
    user:  Optional[str] = None,
):
    """Exporte le journal opérateur en CSV."""
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt   = datetime.fromisoformat(end)   if end   else None
    csv_bytes = data_manager.export_operator_actions_csv(start=start_dt, end=end_dt, user=user)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=journal_operateur.csv"},
    )
