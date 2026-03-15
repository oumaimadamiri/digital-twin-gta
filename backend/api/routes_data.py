"""
api/routes_data.py — Endpoints pour les données temps réel et l'historique
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import io

from services.data_manager import data_manager
from simulation.fake_api import fake_api
from core.config import REDIS_KEY_SIMULATION

router = APIRouter(prefix="/data", tags=["Données"])


@router.get("/current")
def get_current():
    """Retourne le dernier snapshot NOMINAL (réel) depuis Redis.
    Fallback sur fake_api en mémoire si Redis est indisponible ou vide.
    """
    data = None
    try:
        data = data_manager.get_from_cache()
    except Exception:
        pass

    if data is None:
        # Redis down ou clé absente (FakeAPI pas encore écrit) → mémoire directe
        params = fake_api.get_current()
        if params is not None:
            data = params.model_dump(mode="json")

    if data is None:
        raise HTTPException(status_code=503, detail="FakeAPI pas encore démarrée")

    return JSONResponse(
        content=data,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/simulated")
def get_simulated():
    """Retourne le dernier snapshot SIMULÉ (sandbox) depuis Redis.
    Fallback sur fake_api en mémoire si Redis est indisponible ou vide.
    """
    data = None
    try:
        data = data_manager.get_from_cache(key=REDIS_KEY_SIMULATION)
    except Exception:
        pass

    if data is None:
        params = fake_api.get_current()
        if params is not None:
            data = params.model_dump(mode="json")

    if data is None:
        raise HTTPException(status_code=503, detail="FakeAPI pas encore démarrée")

    return JSONResponse(
        content=data,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/history")
def get_history(
    start: Optional[datetime] = Query(None, description="Début de plage (ISO 8601)"),
    end:   Optional[datetime] = Query(None, description="Fin de plage (ISO 8601)"),
    limit: int = Query(500, ge=1, le=10_000),
):
    """Retourne l'historique des paramètres sur une plage temporelle."""
    return data_manager.get_history(start=start, end=end, limit=limit)


@router.get("/statistics")
def get_statistics(
    start: Optional[datetime] = Query(None),
    end:   Optional[datetime] = Query(None),
):
    """Calcule les statistiques descriptives (min, max, mean, std, distribution statuts)."""
    return data_manager.get_statistics(start=start, end=end)


@router.get("/export/csv")
def export_csv(
    start: Optional[datetime] = Query(None),
    end:   Optional[datetime] = Query(None),
):
    """Exporte l'historique en CSV."""
    content  = data_manager.export_csv(start=start, end=end)
    filename = f"gta_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/excel")
def export_excel(
    start: Optional[datetime] = Query(None),
    end:   Optional[datetime] = Query(None),
):
    """Exporte l'historique en Excel."""
    content  = data_manager.export_excel(start=start, end=end)
    filename = f"gta_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )