"""
main.py — Point d'entrée FastAPI de la plateforme Digital Twin GTA
Lance le serveur, initialise la base de données et démarre la boucle FakeAPI.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from core.config import API_HOST, API_PORT, DEBUG, ALLOWED_ORIGINS, AI_TRAIN_ON_STARTUP, REDIS_KEY_SIMULATION
from core.database import init_db
from simulation.fake_api import fake_api
from services.data_manager import data_manager
from services.alert_manager import alert_manager
from api.routes_data       import router as data_router
from api.routes_simulation import router as simulation_router
from api.routes_ai         import router as ai_router
from api.routes_settings   import router as settings_router
from api.routes_audit      import router as audit_router
from api.routes_control    import router as control_router


# ─────────────────────────────────────────────
# WEBSOCKET — Connection Manager
# ─────────────────────────────────────────────

class ConnectionManager:
    """Gère les connexions WebSocket actives et diffuse les données."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connecté. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket déconnecté. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.active_connections.remove(d)


ws_manager = ConnectionManager()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gta.main")


# ─────────────────────────────────────────────
# CALLBACK : appelé à chaque nouveau snapshot
# ─────────────────────────────────────────────

async def on_new_data(nominal, simulated):
    """
    Fonction déclenchée toutes les 500ms avec les snapshots GTA.
    - nominal   : destiné au Dashboard (réel) -> Cache + DB + Alertes + WebSocket broadcast
    - simulated : destiné à la page Simulation (sandbox) -> Cache uniquement
    """
    try:
        # 1) Flux NOMINAL (Dashboard principal)
        data_manager.save_to_cache(nominal)

        # Persistance DB (1 point sur 10 = toutes les 5s)
        if not hasattr(on_new_data, "_counter"):
            on_new_data._counter = 0
        on_new_data._counter += 1
        if on_new_data._counter % 10 == 0:
            data_manager.save_to_db(nominal)

        # Vérification des seuils (Dashboard)
        new_alerts = alert_manager.check_thresholds(nominal)
        for alert in new_alerts:
            data_manager.save_alert(alert)
            logger.warning(f"[ALERTE RÉELLE] {alert.parameter} = {alert.value:.2f} | {alert.severity}")

        # 2) Flux SIMULÉ (Sandbox Simulation)
        data_manager.save_to_cache(simulated, key=REDIS_KEY_SIMULATION)

        # 3) Broadcast WebSocket — push instantané vers tous les clients connectés
        if ws_manager.active_connections:
            payload = nominal.model_dump(mode="json")
            payload["timestamp"] = nominal.timestamp.isoformat()
            await ws_manager.broadcast(json.dumps(payload))

    except Exception as exc:
        logger.error(f"Erreur critique dans la boucle de traitement des données : {exc}", exc_info=True)


# ─────────────────────────────────────────────
# LIFESPAN : démarrage / arrêt
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Démarrage ──
    logger.info("Initialisation de la base de données SQLite…")
    init_db()

    if AI_TRAIN_ON_STARTUP:
        logger.info("Entraînement initial de l'autoencodeur sur données nominales…")
        try:
            _train_autoencoder_on_nominal()
        except Exception as exc:
            logger.exception(
                "Échec de l'entraînement initial de l'autoencodeur. "
                "Poursuite du démarrage sans module IA complet : %s",
                exc,
            )
    else:
        logger.info(
            "AI_TRAIN_ON_STARTUP désactivé — saut de l'entraînement "
            "initial de l'autoencodeur."
        )

    logger.info("Purge du cache Redis (évite état stale d'un run précédent)…")
    data_manager.clear_runtime_keys()

    logger.info("Démarrage de la boucle FakeAPI (500ms)…")
    fake_api.set_on_new_data(on_new_data)
    task = asyncio.create_task(fake_api.run())

    logger.info("✅ Plateforme GTA prête.")
    yield

    # ── Arrêt ──
    fake_api.stop()
    task.cancel()
    logger.info("FakeAPI arrêtée.")


def _train_autoencoder_on_nominal():
    """Génère 500 points nominaux et entraîne l'autoencodeur."""
    from ai.autoencoder import autoencoder
    from core.config import NOMINAL
    import random, math

    data = []
    for _ in range(500):
        point = {k: v * (1 + random.gauss(0, 0.005)) for k, v in NOMINAL.items()
                 if isinstance(v, (int, float))}
        data.append(point)
    autoencoder.train(data)
    logger.info("Autoencodeur entraîné sur 500 points nominaux.")


# ─────────────────────────────────────────────
# APPLICATION FASTAPI
# ─────────────────────────────────────────────

app = FastAPI(
    title       = "Digital Twin GTA — API",
    description = "Plateforme de jumeau numérique pour Groupe Turbo-Alternateur",
    version     = "1.0.0",
    docs_url    = "/docs",
    lifespan    = lifespan,
)

# CORS (origines contrôlées via configuration)
if isinstance(ALLOWED_ORIGINS, str):
    if ALLOWED_ORIGINS.strip() == "*":
        cors_origins = ["*"]
    else:
        cors_origins = [
            origin.strip()
            for origin in ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]
else:
    cors_origins = list(ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = cors_origins,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)
# Compression GZIP automatique des réponses JSON >= 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# Routes
app.include_router(data_router)
app.include_router(simulation_router)
app.include_router(ai_router)
app.include_router(settings_router)
app.include_router(audit_router)
app.include_router(control_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "name":    "Digital Twin GTA",
        "status":  "running",
        "version": "1.0.0",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.websocket("/ws/data")
async def websocket_data(websocket: WebSocket):
    """Endpoint WebSocket : pousse le snapshot GTA en temps réel à chaque mise à jour (500ms)."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Maintient la connexion ouverte (le push est fait via broadcast dans on_new_data)
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)



# ─────────────────────────────────────────────
# LANCEMENT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=DEBUG)