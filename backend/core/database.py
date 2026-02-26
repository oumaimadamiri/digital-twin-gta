"""
database.py — Connexions Redis (cache temps réel) et SQLite (historique)
"""

import sqlite3
import json
import redis
from contextlib import contextmanager
from core.config import (
    REDIS_HOST, REDIS_PORT, REDIS_DB,
    SQLITE_PATH
)

# ─────────────────────────────────────────────
# REDIS — Cache temps réel
# ─────────────────────────────────────────────

def get_redis_client() -> redis.Redis:
    """Retourne un client Redis connecté."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )

# Instance globale
redis_client = get_redis_client()


# ─────────────────────────────────────────────
# SQLITE — Historique des paramètres
# ─────────────────────────────────────────────

def init_db():
    """Initialise la base SQLite et crée les tables si elles n'existent pas."""
    import os
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)

    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gta_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL,
                pressure_hp     REAL,
                temperature_hp  REAL,
                steam_flow_hp   REAL,
                pressure_bp     REAL,
                temperature_bp  REAL,
                steam_flow_bp   REAL,
                turbine_speed   REAL,
                active_power    REAL,
                power_factor    REAL,
                efficiency      REAL,
                valve_v1        REAL,
                valve_v2        REAL,
                valve_v3        REAL,
                status          TEXT,
                scenario        TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                alert_type  TEXT,
                parameter   TEXT,
                value       REAL,
                threshold   REAL,
                severity    TEXT,
                source      TEXT,
                acknowledged INTEGER DEFAULT 0
            )
        """)
        # ── Index pour accélérer les requêtes historiques ────────────
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_timestamp
            ON gta_history (timestamp DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_status
            ON gta_history (status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
            ON alerts (timestamp DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged
            ON alerts (acknowledged)
        """)
        conn.commit()


@contextmanager
def get_db():
    """Context manager pour une connexion SQLite."""
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # accès par nom de colonne
    conn.execute("PRAGMA journal_mode=WAL")  # écriture concurrent rapide
    conn.execute("PRAGMA synchronous=NORMAL") # équilibre sécurité/vitesse
    conn.execute("PRAGMA cache_size=-32000")  # 32 MB cache mémoire
    try:
        yield conn
    finally:
        conn.close()