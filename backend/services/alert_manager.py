"""
services/alert_manager.py — Vérification des seuils et création d'alertes.
Première ligne de défense avant le module IA.
"""

from datetime import datetime
from typing import List

from core.config import THRESHOLDS
from models.gta_parameters import GTAParameters
from models.alert import Alert, AlertType, SeverityLevel, AlertSource


class AlertManager:

    def __init__(self):
        # Seuils configurables (copie modifiable à chaud)
        self._thresholds = {k: v.copy() for k, v in THRESHOLDS.items()}
        # Alertes actives en mémoire (non acquittées)
        self._active_alerts: List[Alert] = []

    # ──────────────────────────────────────────
    # VÉRIFICATION DES SEUILS
    # ──────────────────────────────────────────

    def check_thresholds(self, params: GTAParameters) -> List[Alert]:
        """
        Compare chaque paramètre à ses seuils min/max.
        Retourne la liste des nouvelles alertes créées.
        """
        new_alerts: List[Alert] = []
        params_dict = params.model_dump()

        for param, limits in self._thresholds.items():
            value = params_dict.get(param)
            if value is None:
                continue

            min_val = limits["min"]
            max_val = limits["max"]

            if value < min_val:
                alert = self._build_alert(
                    param     = param,
                    value     = value,
                    threshold = min_val,
                    direction = "below",
                )
                new_alerts.append(alert)
                self._active_alerts.append(alert)

            elif value > max_val:
                alert = self._build_alert(
                    param     = param,
                    value     = value,
                    threshold = max_val,
                    direction = "above",
                )
                new_alerts.append(alert)
                self._active_alerts.append(alert)

        # Garde les 200 alertes actives les plus récentes en mémoire
        self._active_alerts = self._active_alerts[-200:]
        return new_alerts

    def _build_alert(self, param: str, value: float,
                     threshold: float, direction: str) -> Alert:
        """Construit une alerte et détermine sa sévérité."""
        deviation = abs(value - threshold) / (threshold + 1e-9)

        if deviation > 0.10:
            severity = SeverityLevel.CRITICAL
        elif deviation > 0.04:
            severity = SeverityLevel.WARNING
        else:
            severity = SeverityLevel.INFO

        label = "en dessous" if direction == "below" else "au-dessus"
        return Alert(
            timestamp  = datetime.utcnow(),
            alert_type = AlertType.THRESHOLD_EXCEEDED,
            parameter  = param,
            value      = round(value, 3),
            threshold  = threshold,
            severity   = severity,
            source     = AlertSource.THRESHOLD,
            message    = f"{param} = {value:.2f} est {label} du seuil {threshold:.2f}",
        )

    # ──────────────────────────────────────────
    # ALERTES IA
    # ──────────────────────────────────────────

    def add_ai_alert(self, param: str, value: float,
                     threshold: float, message: str = "") -> Alert:
        """Crée une alerte issue du module IA."""
        alert = Alert(
            timestamp  = datetime.utcnow(),
            alert_type = AlertType.ANOMALY_DETECTED,
            parameter  = param,
            value      = round(value, 4),
            threshold  = threshold,
            severity   = SeverityLevel.WARNING,
            source     = AlertSource.AI,
            message    = message or f"Anomalie IA détectée sur {param}",
        )
        self._active_alerts.append(alert)
        return alert

    # ──────────────────────────────────────────
    # ACCESSEURS
    # ──────────────────────────────────────────

    def get_active_alerts(self) -> List[Alert]:
        return list(self._active_alerts)

    def clear_alerts(self):
        self._active_alerts.clear()

    def update_thresholds(self, new_thresholds: dict):
        """Met à jour les seuils à chaud (sans redémarrage)."""
        for param, limits in new_thresholds.items():
            if param in self._thresholds:
                self._thresholds[param].update(limits)

    def get_thresholds(self) -> dict:
        return {k: v.copy() for k, v in self._thresholds.items()}


# Instance globale
alert_manager = AlertManager()