"""
services/data_manager.py — Persistance des données
Gère l'écriture/lecture dans Redis (temps réel) et SQLite (historique).
"""

import json
import io
import logging
from datetime import datetime
from typing import List, Optional

import pandas as pd
from redis.exceptions import RedisError

from core.config import REDIS_KEY_CURRENT, REDIS_KEY_STATE
from core.database import redis_client, get_db
from models.gta_parameters import GTAParameters
from models.alert import Alert


logger = logging.getLogger("gta.data_manager")


class DataManager:

    # ──────────────────────────────────────────
    # REDIS — Cache temps réel
    # ──────────────────────────────────────────

    def save_to_cache(self, params: GTAParameters, key: str = REDIS_KEY_CURRENT):
        """Stocke le snapshot courant dans Redis (TTL 10s)."""
        data = params.model_dump(mode="json")
        # datetime → str pour JSON
        data["timestamp"] = params.timestamp.isoformat()
        try:
            redis_client.setex(key, 10, json.dumps(data))
        except RedisError as exc:
            # En cas d'indisponibilité de Redis, on loggue un avertissement mais
            # on ne bloque pas le pipeline principal de données.
            logger.warning("Impossible d'écrire dans Redis : %s", exc)

    def get_from_cache(self, key: str = REDIS_KEY_CURRENT) -> Optional[dict]:
        """Récupère le dernier snapshot depuis Redis."""
        try:
            raw = redis_client.get(key)
        except RedisError as exc:
            logger.warning("Impossible de lire dans Redis : %s", exc)
            return None

        if not raw:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Valeur Redis invalide pour %s : %s", REDIS_KEY_CURRENT, exc)
            return None

    # ──────────────────────────────────────────
    # SQLITE — Historique
    # ──────────────────────────────────────────

    def save_to_db(self, params: GTAParameters):
        """Insère un snapshot en base SQLite."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO gta_history (
                    timestamp, pressure_hp, temperature_hp, steam_flow_hp,
                    pressure_bp, temperature_bp, steam_flow_bp,
                    turbine_speed, active_power, power_factor, efficiency,
                    valve_v1, valve_v2, valve_v3, status, scenario
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                params.timestamp.isoformat(),
                params.pressure_hp, params.temperature_hp, params.steam_flow_hp,
                params.pressure_bp, params.temperature_bp, params.steam_flow_bp,
                params.turbine_speed, params.active_power, params.power_factor,
                params.efficiency, params.valve_v1, params.valve_v2, params.valve_v3,
                params.status, params.scenario,
            ))
            conn.commit()

    def get_history(
        self,
        start: Optional[datetime] = None,
        end:   Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[dict]:
        """Récupère l'historique sur une plage temporelle."""
        with get_db() as conn:
            query  = "SELECT * FROM gta_history WHERE 1=1"
            params = []
            if start:
                query += " AND timestamp >= ?"
                params.append(start.isoformat())
            if end:
                query += " AND timestamp <= ?"
                params.append(end.isoformat())
            query += f" ORDER BY timestamp DESC LIMIT {limit}"

            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_statistics(self, start: Optional[datetime] = None,
                       end: Optional[datetime] = None) -> dict:
        """Calcule les statistiques descriptives sur une période."""
        history = self.get_history(start, end, limit=10_000)
        if not history:
            return {}
        df = pd.DataFrame(history)
        numeric_cols = [
            "pressure_hp", "temperature_hp", "steam_flow_hp",
            "turbine_speed", "active_power", "power_factor", "efficiency"
        ]
        stats = {}
        for col in numeric_cols:
            if col in df.columns:
                stats[col] = {
                    "min":   round(float(df[col].min()), 2),
                    "max":   round(float(df[col].max()), 2),
                    "mean":  round(float(df[col].mean()), 2),
                    "std":   round(float(df[col].std()), 2),
                }
        # Distribution des statuts
        if "status" in df.columns:
            counts = df["status"].value_counts().to_dict()
            total  = len(df)
            stats["status_distribution"] = {
                k: {"count": v, "pct": round(v / total * 100, 1)}
                for k, v in counts.items()
            }
        return stats

    def export_csv(self, start=None, end=None) -> bytes:
        """Exporte l'historique en CSV (bytes)."""
        data = self.get_history(start, end, limit=50_000)
        df   = pd.DataFrame(data)
        return df.to_csv(index=False).encode("utf-8")

    def export_excel(self, start=None, end=None) -> bytes:
        """Exporte l'historique en Excel (bytes)."""
        data   = self.get_history(start, end, limit=50_000)
        df     = pd.DataFrame(data)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="GTA_History")
        return buffer.getvalue()

    # ──────────────────────────────────────────
    # ALERTES
    # ──────────────────────────────────────────

    def save_alert(self, alert: Alert):
        with get_db() as conn:
            conn.execute("""
                INSERT INTO alerts
                (timestamp, alert_type, parameter, value, threshold, severity, source)
                VALUES (?,?,?,?,?,?,?)
            """, (
                alert.timestamp.isoformat(),
                alert.alert_type, alert.parameter,
                alert.value, alert.threshold,
                alert.severity, alert.source,
            ))
            conn.commit()

    def get_alerts(self, limit: int = 100, only_active: bool = False) -> List[dict]:
        with get_db() as conn:
            query  = "SELECT * FROM alerts"
            if only_active:
                query += " WHERE acknowledged = 0"
            query += f" ORDER BY timestamp DESC LIMIT {limit}"
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def acknowledge_alert(self, alert_id: int):
        with get_db() as conn:
            conn.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,)
            )
            conn.commit()


# Instance globale
data_manager = DataManager()