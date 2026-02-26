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