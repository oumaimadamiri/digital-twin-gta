"""
models/alert.py — Schémas Pydantic pour les alertes
"""

from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional


class AlertType(str, Enum):
    THRESHOLD_EXCEEDED = "THRESHOLD_EXCEEDED"
    ANOMALY_DETECTED   = "ANOMALY_DETECTED"
    PREDICTION_WARNING = "PREDICTION_WARNING"


class SeverityLevel(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class AlertSource(str, Enum):
    THRESHOLD = "SEUIL"
    AI        = "IA"


class Alert(BaseModel):
    id:           Optional[int] = None
    timestamp:    datetime = Field(default_factory=datetime.utcnow)
    alert_type:   AlertType
    parameter:    str
    value:        float
    threshold:    float
    severity:     SeverityLevel
    source:       AlertSource
    acknowledged: bool = False
    message:      str = ""

    class Config:
        use_enum_values = True