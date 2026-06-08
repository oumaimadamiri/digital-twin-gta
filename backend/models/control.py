"""
models/control.py — Schémas Pydantic pour la couche Contrôle Commande
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class ControlMode(str, Enum):
    MANUAL = "MANUAL"
    AUTO   = "AUTO"


class RegulationTarget(str, Enum):
    POWER    = "POWER"     # PID puissance asservit V1 (défaut)
    PRESSURE = "PRESSURE"  # PID pression HP asservit V1


class SequenceState(str, Enum):
    IDLE     = "IDLE"
    STARTING = "STARTING"
    STOPPING = "STOPPING"
    TRIPPED  = "TRIPPED"


class Setpoints(BaseModel):
    power_mw:         Optional[float] = Field(None, ge=0, le=30,   description="Consigne puissance active (MW)")
    speed_rpm:        Optional[float] = Field(None, ge=0, le=7000,  description="Consigne vitesse (RPM) — informatif")
    pressure_hp_bar:  Optional[float] = Field(None, ge=0, le=80,   description="Consigne pression HP (bar) — informatif")


class RegulationTargetRequest(BaseModel):
    target:   RegulationTarget
    operator: str = "Opérateur"


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
    loop:     str   = Field("power", description="Boucle cible : power | speed | pressure")
    operator: str   = "Opérateur"


class SequenceCommand(BaseModel):
    sequence: Literal["start_turbine", "stop_turbine"]
    operator: str = "Opérateur"


class EmergencyTripCommand(BaseModel):
    confirm:  bool = Field(False, description="Doit être True pour confirmer l'arrêt d'urgence")
    operator: str  = "Opérateur"


class ValveControlCommand(BaseModel):
    """Commande manuelle d'une vanne — refusée si mode AUTO."""
    valve_v1:       Optional[float] = Field(None, ge=0, le=100)
    valve_v2:       Optional[float] = Field(None, ge=0, le=100)
    valve_v3:       Optional[float] = Field(None, ge=0, le=100)
    valve_bp:       Optional[float] = Field(None, ge=0, le=100)
    valve_bp_admit: Optional[float] = Field(None, ge=0, le=100)
    operator: str = "Opérateur"


# ── AVR / Excitation ──

class AVRMode(str, Enum):
    OFF    = "OFF"
    VOLTAGE = "VOLTAGE"
    COSPHI  = "COSPHI"
    MANUAL  = "MANUAL"


class AVRModeCommand(BaseModel):
    mode:     AVRMode
    operator: str = "Opérateur"


class AVRSetpointCommand(BaseModel):
    voltage_kv: Optional[float] = Field(None, ge=9.0, le=12.0, description="Consigne tension (kV)")
    cosphi:     Optional[float] = Field(None, ge=0.7, le=1.0,  description="Consigne cos φ")
    operator:   str = "Opérateur"


class AVRGainsCommand(BaseModel):
    k_a:      float = Field(..., ge=0,     description="Gain K_A du régulateur")
    t_a:      float = Field(..., ge=0.001, description="Constante de temps T_A (s)")
    operator: str   = "Opérateur"


class AVRManualCommand(BaseModel):
    e_fd_pu:  float = Field(..., ge=0.0, le=5.0, description="Tension excitation manuelle (p.u.)")
    operator: str   = "Opérateur"


# ── Désurchauffeur (Phase 1 — B.3) ──

class AttemperatorSetpointCommand(BaseModel):
    setpoint_c: float = Field(..., ge=300.0, le=520.0, description="Consigne T° HP désurchauffeur (°C)")
    operator: str = "Opérateur"


class AttemperatorEnableCommand(BaseModel):
    enabled: bool
    operator: str = "Opérateur"


# ── Condenseur (Phase 1 — B.4) ──

class CondLevelSetpointCommand(BaseModel):
    setpoint_pct: float = Field(..., ge=10.0, le=90.0, description="Consigne niveau hotwell (%)")
    operator: str = "Opérateur"


class CondVacuumSetpointCommand(BaseModel):
    setpoint_mbar: float = Field(..., ge=20.0, le=150.0, description="Consigne vide condenseur (mbar)")
    operator: str = "Opérateur"


class BarrageWarmupCommand(BaseModel):
    seconds:  float = Field(..., ge=300.0, le=600.0,
                            description="Durée préchauffage barrage (s) — entre 300 s (5 min) et 600 s (10 min)")
    operator: str   = "Opérateur"


class OperatorAction(BaseModel):
    """Corps minimal pour les endpoints n'ayant besoin que du nom opérateur."""
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
    # AVR
    avr_mode:             str            = "VOLTAGE"
    avr_voltage_setpoint: float          = 10.5
    avr_cosphi_setpoint:  float          = 0.85
    avr_e_fd_pu:          float          = 1.0
    avr_saturated:        bool           = False
    avr_k_a:              float          = 200.0
    avr_t_a:              float          = 0.05
