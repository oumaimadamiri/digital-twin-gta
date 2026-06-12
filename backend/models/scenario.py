"""
models/scenario.py — Schéma Pydantic pour les scénarios de perturbation
"""

from pydantic import BaseModel, Field
from typing import Dict, Optional


class Scenario(BaseModel):
    id:               int
    name:             str
    description:      str
    perturbation_type: str           # "ramp" | "step" | "oscillation"
    # Modifications cibles : {param_name: delta ou valeur absolue}
    target_deltas:    Dict[str, float]
    duration_s:       int = Field(60, description="Durée de la perturbation en secondes")
    active:           bool = False


class ScenarioTrigger(BaseModel):
    scenario_id: int


class ResetCommand(BaseModel):
    confirm: bool = True

class ESVCommand(BaseModel):
    open: bool
    operator: str = "Opérateur"


class LubricationOffsetCommand(BaseModel):
    press_offset: float = Field(0.0, ge=-1.5, le=1.5,  description="Offset pression huile (bar)")
    temp_offset:  float = Field(0.0, ge=-20.0, le=40.0, description="Offset température huile (°C)")
    operator: str = "Opérateur"

class SandboxCommand(BaseModel):
    active: bool
    operator: str = "Opérateur"