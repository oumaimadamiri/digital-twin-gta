"""
services/data_manager.py — Persistance des données
Gère l'écriture/lecture dans Redis (temps réel) et SQLite (historique).
"""

import json
import io
import logging
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
from redis.exceptions import RedisError

from core.config import REDIS_KEY_CURRENT, REDIS_KEY_SIMULATION, REDIS_KEY_STATE
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

    def clear_runtime_keys(self):
        """Supprime les clés Redis de snapshot au démarrage pour éviter un état stale."""
        try:
            redis_client.delete(REDIS_KEY_CURRENT, REDIS_KEY_SIMULATION, REDIS_KEY_STATE)
            logger.info("Clés Redis runtime purgées au démarrage.")
        except RedisError as exc:
            logger.warning("Impossible de purger les clés Redis : %s", exc)

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

    # APRÈS
    def save_to_db(self, params: GTAParameters):
        with get_db() as conn:
            conn.execute("""
                INSERT INTO gta_history (
                    timestamp, pressure_hp, temperature_hp, steam_flow_hp,
                    pressure_bp_in, temperature_bp, steam_flow_bp_in,
                    steam_flow_condenser, pressure_bp_barillet,
                    pressure_condenser,
                    turbine_speed, active_power, reactive_power, apparent_power,
                    power_factor, voltage, current_a, efficiency,
                    valve_v1, valve_v2, valve_v3, valve_bp,
                    status, scenario
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                (
                params.timestamp.isoformat(),
                params.pressure_hp, params.temperature_hp, params.steam_flow_hp,
                params.pressure_bp_in, params.temperature_bp, params.steam_flow_bp_in,
                params.steam_flow_condenser, params.pressure_bp_barillet,
                params.pressure_condenser,
                params.turbine_speed, params.active_power, params.reactive_power,
                params.apparent_power,
                params.power_factor, params.voltage, params.current_a, params.efficiency,
                params.valve_v1, params.valve_v2, params.valve_v3,
                params.valve_bp, params.status, params.scenario,
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
                # Compare as datetime, not raw text, and ignore timezone/microseconds
                # by normalizing stored ISO timestamp to first 19 chars (YYYY-MM-DDTHH:MM:SS).
                query += " AND datetime(replace(substr(timestamp, 1, 19), 'T', ' ')) >= datetime(?)"
                params.append(start.strftime("%Y-%m-%d %H:%M:%S"))
            if end:
                query += " AND datetime(replace(substr(timestamp, 1, 19), 'T', ' ')) <= datetime(?)"
                params.append(end.strftime("%Y-%m-%d %H:%M:%S"))
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
            "pressure_bp_in", "temperature_bp", "steam_flow_bp_in",
            "steam_flow_condenser", "pressure_bp_barillet", "pressure_condenser",
            "turbine_speed", "active_power", "reactive_power", "apparent_power",
            "power_factor", "voltage", "current_a", "efficiency"
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

    def _filter_columns(self, df: pd.DataFrame, params=None) -> pd.DataFrame:
        """Restreint les colonnes au filtre `params` (timestamp + status conservés)."""
        if not params:
            return df
        keep = ["timestamp", "status"] + [p for p in params if p not in ("timestamp", "status")]
        keep = [c for c in keep if c in df.columns]
        return df[keep] if keep else df

    def export_csv(self, start=None, end=None, params=None) -> bytes:
        """Exporte l'historique en CSV (bytes). `params` filtre les colonnes."""
        data = self.get_history(start, end, limit=50_000)
        df   = self._filter_columns(pd.DataFrame(data), params)
        return df.to_csv(index=False).encode("utf-8")

    def export_excel(self, start=None, end=None, params=None) -> bytes:
        """Exporte l'historique en Excel (bytes). `params` filtre les colonnes."""
        data   = self.get_history(start, end, limit=50_000)
        df     = self._filter_columns(pd.DataFrame(data), params)
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

    def acknowledge_alert(self, alert_id: int, user: str = "Opérateur"):
        from core.config import TIMEZONE_OFFSET
        ack_ts = (datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)).isoformat()
        with get_db() as conn:
            conn.execute(
                "UPDATE alerts SET acknowledged = 1, ack_ts = ?, ack_user = ? WHERE id = ?",
                (ack_ts, user, alert_id),
            )
            conn.commit()

    # ──────────────────────────────────────────
    # JOURNAL OPÉRATEUR
    # ──────────────────────────────────────────

    def log_operator_action(
        self,
        user: str,
        action_type: str,
        target: str = None,
        value_before: str = None,
        value_after: str = None,
        source: str = "OPERATOR",
        notes: str = None,
    ):
        """Persiste une action opérateur dans le journal d'audit."""
        from core.config import TIMEZONE_OFFSET
        ts = (datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)).isoformat()
        with get_db() as conn:
            conn.execute(
                """INSERT INTO operator_actions
                   (ts, user, action_type, target, value_before, value_after, source, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (ts, user, action_type, target, value_before, value_after, source, notes),
            )
            conn.commit()
        logger.info("[JOURNAL] %s | %s | %s | %s → %s", user, action_type, target, value_before, value_after)

    def get_operator_actions(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        user: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        """Récupère le journal des actions opérateur."""
        with get_db() as conn:
            query = "SELECT * FROM operator_actions WHERE 1=1"
            params = []
            if start:
                query += " AND datetime(replace(substr(ts,1,19),'T',' ')) >= datetime(?)"
                params.append(start.strftime("%Y-%m-%d %H:%M:%S"))
            if end:
                query += " AND datetime(replace(substr(ts,1,19),'T',' ')) <= datetime(?)"
                params.append(end.strftime("%Y-%m-%d %H:%M:%S"))
            if user:
                query += " AND user = ?"
                params.append(user)
            query += f" ORDER BY ts DESC LIMIT {limit}"
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def export_operator_actions_csv(self, start=None, end=None, user=None) -> bytes:
        data = self.get_operator_actions(start=start, end=end, user=user, limit=10_000)
        return pd.DataFrame(data).to_csv(index=False).encode("utf-8")

    # ──────────────────────────────────────────
    # KV STORE — persistance générique
    # ──────────────────────────────────────────

    def get_kv(self, key: str) -> Optional[str]:
        """Lit une valeur persistée par clé. Retourne None si absente."""
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT value FROM kv_store WHERE key = ?", (key,)
                ).fetchone()
            return row[0] if row else None
        except Exception as exc:
            logger.warning("get_kv(%s) échec : %s", key, exc)
            return None

    def set_kv(self, key: str, value: str) -> None:
        """Persiste une valeur par clé (upsert idempotent)."""
        try:
            ts = datetime.utcnow().isoformat()
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO kv_store(key, value, updated_at) VALUES(?,?,?)
                       ON CONFLICT(key) DO UPDATE SET
                           value      = excluded.value,
                           updated_at = excluded.updated_at""",
                    (key, str(value), ts),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("set_kv(%s) échec : %s", key, exc)


# Instance globale
data_manager = DataManager()