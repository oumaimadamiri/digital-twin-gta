"""
models/gta_parameters.py — Schémas Pydantic des données du GTA
Mis à jour : ajout vannes valve_mp/valve_bp, signaux électriques calculés,
             séparation flux BP entrée / condenseur.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum
import math


class StatusEnum(str, Enum):
    NORMAL   = "NORMAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class GTAParameters(BaseModel):
    """
    Snapshot complet des paramètres GTA en régime permanent.

    Flux vapeur — distinction importante :
      steam_flow_hp       : débit HP entrant (120 T/h nominal)
      steam_flow_condenser: débit vapeur HP détendue vers condenseur (74 T/h)
      steam_flow_bp_in    : débit VP BP entrant depuis source externe (64 T/h)
                            — utilisé au démarrage, quasi nul en régime permanent
    """
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # ── Vapeur haute pression ──
    pressure_hp:    float = Field(..., description="Pression HP (bar)")
    temperature_hp: float = Field(..., description="Température HP (°C)")
    steam_flow_hp:  float = Field(..., description="Débit vapeur HP entrant (T/h)")

    # ── Vapeur basse pression — entrée source externe ──
    pressure_bp_in:    float = Field(..., description="Pression BP entrée source (bar)")
    temperature_bp:    float = Field(..., description="Température BP (°C)")
    steam_flow_bp_in:  float = Field(0.0, description="Débit VP BP entrant source externe (T/h)")

    # ── Sorties vapeur ──
    steam_flow_condenser:   float = Field(..., description="Débit vapeur vers condenseur (T/h)")
    pressure_bp_barillet:   float = Field(..., description="Pression VP BP vers barillet (bar)")
    pressure_condenser:     float = Field(..., description="Pression condenseur / vide (bar)")

    # ── Turbine ──
    turbine_speed: float = Field(..., description="Vitesse turbine (RPM)")

    # ── Alternateur — signaux électriques ──
    active_power:    float = Field(..., description="Puissance active P (MW)")
    reactive_power:  float = Field(..., description="Puissance réactive Q (MVAR)")
    apparent_power:  float = Field(..., description="Puissance apparente S (MVA)")
    power_factor:    float = Field(..., description="Facteur de puissance cos φ")
    voltage:         float = Field(..., description="Tension nominale (kV)")
    current_a:       float = Field(..., description="Courant de ligne I (A)")

    # ── Vannes ──
    # V1 : admission HP principale (80% débit)
    valve_v1: float = Field(..., ge=0, le=100, description="Vanne V1 admission HP (%)")
    # V2, V3 : équilibrage mécanique pur (ne modifient pas le bilan thermo)
    valve_v2: float = Field(..., ge=0, le=100, description="Vanne V2 équilibrage (%)")
    valve_v3: float = Field(..., ge=0, le=100, description="Vanne V3 équilibrage (%)")
    # Vanne extraction MP → barillet
    valve_mp: float = Field(..., ge=0, le=100, description="Vanne extraction MP (%)")
    # Vanne sortie BP → condenseur
    valve_bp: float = Field(..., ge=0, le=100, description="Vanne sortie BP condenseur (%)")

    # ── Rendement et état ──
    efficiency: float = Field(..., description="Rendement thermodynamique (%)")
    status:     StatusEnum = StatusEnum.NORMAL
    scenario:   Optional[str] = None

    class Config:
        use_enum_values = True

    # ── Propriétés dérivées (lecture seule) ──
    @property
    def is_overpowered(self) -> bool:
        """True si la puissance dépasse 24 MW → risque surpression BP barillet."""
        return self.active_power > 24.0

    @property
    def load_ratio(self) -> float:
        """Ratio de charge (0–1) par rapport à la puissance nominale 24 MW."""
        return min(self.active_power / 24.0, 1.5)


class ValveCommand(BaseModel):
    """Commande opérateur sur les vannes."""
    valve_v1: Optional[float] = Field(None, ge=0, le=100, description="V1 admission HP (%)")
    valve_v2: Optional[float] = Field(None, ge=0, le=100, description="V2 équilibrage (%)")
    valve_v3: Optional[float] = Field(None, ge=0, le=100, description="V3 équilibrage (%)")
    valve_mp: Optional[float] = Field(None, ge=0, le=100, description="Vanne extraction MP (%)")
    valve_bp: Optional[float] = Field(None, ge=0, le=100, description="Vanne sortie BP (%)")