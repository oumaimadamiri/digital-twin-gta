"""
models/gta_parameters.py — Schémas Pydantic des données du GTA
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class StatusEnum(str, Enum):
    NORMAL   = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class GTAParameters(BaseModel):
    """Snapshot complet des paramètres GTA à un instant donné."""
    timestamp:      datetime = Field(default_factory=datetime.utcnow)

    pressure_hp:    float = Field(..., description="Pression HP (bar)")
    temperature_hp: float = Field(..., description="Température HP (°C)")
    steam_flow_hp:  float = Field(..., description="Débit vapeur HP (T/h)")

    pressure_bp:    float = Field(..., description="Pression BP (bar)")
    temperature_bp: float = Field(..., description="Température BP (°C)")
    steam_flow_bp:  float = Field(..., description="Débit vapeur BP (T/h)")

    turbine_speed:  float = Field(..., description="Vitesse turbine (RPM)")

    active_power:   float = Field(..., description="Puissance active (MW)")
    power_factor:   float = Field(..., description="Facteur de puissance cos φ")

    valve_v1:       float = Field(..., ge=0, le=100, description="Vanne V1 (%)")
    valve_v2:       float = Field(..., ge=0, le=100, description="Vanne V2 (%)")
    valve_v3:       float = Field(..., ge=0, le=100, description="Vanne V3 (%)")

    efficiency:     float = Field(..., description="Rendement thermodynamique (%)")
    status:         StatusEnum = StatusEnum.NORMAL
    scenario:       Optional[str] = None

    class Config:
        use_enum_values = True


class ValveCommand(BaseModel):
    valve_v1: Optional[float] = Field(None, ge=0, le=100)
    valve_v2: Optional[float] = Field(None, ge=0, le=100)
    valve_v3: Optional[float] = Field(None, ge=0, le=100)