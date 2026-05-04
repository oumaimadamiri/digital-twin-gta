"""
models/control.py — Schémas Pydantic pour la couche Contrôle Commande
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class ControlMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO   = "AUTO"


class SequenceState(str, Enum):
    IDLE     = "IDLE"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    TRIPPED  = "TRIPPED"


class Setpoints(BaseModel):
    power_mw:         Optional[float] = Field(None, ge=0, le=30,   description="Consigne puissance active (MW)")
    speed_rpm:        Optional[float] = Field(None, ge=0, le=7000,  description="Consigne vitesse (RPM) — informatif")
    pressure_hp_bar:  Optional[float] = Field(None, ge=0, le=80,   description="Consigne pression HP (bar) — informatif")


class ModeCommand(BaseModel):
    mode:     ControlMode
    operator: str = "Opérateur"


class SetpointsCommand(BaseModel):
    setpoints: Setpoints
    operator:  str = "Opérateur"


class PIDTuningCommand(BaseModel):
    kp:       float = Field(..., ge=0, description="Gain proportionnel")
    ki:       float = Field(..., ge=0, description="Gain intégral")
    kd:       float = Field(..., ge=0, description="Gain dérivé")
    operator: str   = "Opérateur"


class SequenceCommand(BaseModel):
    sequence: Literal["start_turbine", "stop_turbine"]
    operator: str = "Opérateur"


class EmergencyTripCommand(BaseModel):
    confirm:  bool = Field(False, description="Doit être True pour confirmer l'arrêt d'urgence")
    operator: str  = "Opérateur"


class ValveControlCommand(BaseModel):
    """Commande manuelle d'une vanne — refusée si mode AUTO."""
    valve_v1: Optional[float] = Field(None, ge=0, le=100)
    valve_v2: Optional[float] = Field(None, ge=0, le=100)
    valve_v3: Optional[float] = Field(None, ge=0, le=100)
    valve_bp: Optional[float] = Field(None, ge=0, le=100)
    operator: str = "Opérateur"


class ControlState(BaseModel):
    mode:                    ControlMode   = ControlMode.MANUAL
    setpoint_power_mw:       Optional[float] = None
    setpoint_speed_rpm:      Optional[float] = None
    setpoint_pressure_hp_bar: Optional[float] = None
    pid_kp:                  float = 2.0
    pid_ki:                  float = 0.5
    pid_kd:                  float = 0.05
    pid_error:               Optional[float] = None
    pid_output:              Optional[float] = None
    sequence_state:          SequenceState = SequenceState.IDLE
    sequence_progress:       Optional[float] = None
    tripped:                 bool  = False
    interlock_warnings:      list  = []
    valve_state:             dict  = {}
