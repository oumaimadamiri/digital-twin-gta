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
    """Retourne un client Redis connecté avec stratégie de retry."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30
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

    # Liste des colonnes critiques nécessaires au bilan complet actuel
    required_columns = [
        "voltage", "charge_site", "excedent_reseau",
        "flow_v1_th", "flow_v2_th", "flow_v3_th",
        "flow_barillet_in", "flow_chauffage_as", "flow_surchauffeur"
    ]

    with sqlite3.connect(SQLITE_PATH) as conn:
        cursor = conn.cursor()
        
        # Vérification du schéma existant
        cursor.execute("PRAGMA table_info(gta_history)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # Si la table existe mais manque d'au moins une colonne requise, on la recrée
        if existing_columns:
            missing = [col for col in required_columns if col not in existing_columns]
            if missing:
                print(f"Migration: Colonnes manquantes détectées ({missing}). Recréation de gta_history...")
                conn.execute("DROP TABLE gta_history")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS gta_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT    NOT NULL,
                pressure_hp     REAL,
                temperature_hp  REAL,
                steam_flow_hp   REAL,
                pressure_bp_in  REAL,
                temperature_bp  REAL,
                steam_flow_bp_in REAL,
                steam_flow_condenser REAL,
                pressure_bp_barillet REAL,
                pressure_condenser REAL,
                turbine_speed   REAL,
                active_power    REAL,
                reactive_power  REAL,
                apparent_power  REAL,
                power_factor    REAL,
                voltage         REAL,
                current_a       REAL,
                efficiency      REAL,
                valve_v1        REAL,
                valve_v2        REAL,
                valve_v3        REAL,
                valve_bp        REAL,
                charge_site      REAL,
                excedent_reseau  REAL,
                flow_v1_th       REAL,
                flow_v2_th       REAL,
                flow_v3_th       REAL,
                flow_barillet_in    REAL,
                flow_chauffage_as REAL,
                flow_surchauffeur REAL,
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