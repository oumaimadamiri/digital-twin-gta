"""
models/gta_parameters.py — Schémas Pydantic des données du GTA
Mis à jour : ajout vanne valve_bp, signaux électriques calculés,
             extraction intermédiaire à taux fixe (38% spec).
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
    valve_v1_target: float = Field(100.0, ge=0, le=100, description="Consigne Vanne V1 (%)")
    # V2, V3 : équilibrage mécanique pur (ne modifient pas le bilan thermo)
    valve_v2: float = Field(..., ge=0, le=100, description="Vanne V2 équilibrage (%)")
    valve_v2_target: float = Field(100.0, ge=0, le=100, description="Consigne Vanne V2 (%)")
    valve_v3: float = Field(..., ge=0, le=100, description="Vanne V3 équilibrage (%)")
    valve_v3_target: float = Field(100.0, ge=0, le=100, description="Consigne Vanne V3 (%)")
    # Vanne sortie BP → condenseur
    valve_bp: float = Field(..., ge=0, le=100, description="Vanne sortie BP condenseur (%)")
    valve_bp_target: float = Field(80.0, ge=0, le=100, description="Consigne Vanne BP (%)")

    # ── Auxiliaires & Mécanique ──
    vib_bearing_fwd: float = Field(2.1, description="Vibration Palier Avant (mm/s)")
    vib_bearing_aft: float = Field(1.8, description="Vibration Palier Arrière (mm/s)")
    temp_bearing_fwd: float = Field(74.0, description="Temp. Palier Avant (°C)")
    temp_bearing_aft: float = Field(76.0, description="Temp. Palier Arrière (°C)")
    lube_oil_press: float = Field(1.5, description="Pression Huile de Graissage (bar)")
    lube_oil_temp: float = Field(45.0, description="Température Huile de Graissage entrée paliers (°C)")
    lube_oil_temp_out:   float = Field(60.0, description="Temp. Huile sortie paliers (°C)")
    lube_oil_tank_level: float = Field(80.0, description="Niveau réservoir huile (%)")
    lube_oil_pump:       str   = Field("MAIN", description="État pompe huile: MAIN | AUX | OFF")
    lube_oil_filter_dp:  float = Field(0.3, description="ΔP filtre huile (bar)")
    axial_displacement: float = Field(0.2, description="Déplacement Axial Rotor (mm)")
    casing_expansion: float = Field(5.0, description="Dilatation Corps (mm)")
    grid_frequency: float = Field(50.00, description="Fréquence Réseau (Hz)")

    # ── Débits hydrauliques par vanne (informatifs) ──
    flow_v1_th:  float = Field(96.0,  description="Débit hydraulique V1 (T/h) = 80% de 120")
    flow_v2_th:  float = Field(8.4,   description="Débit hydraulique V2 (T/h) = ~7%")
    flow_v3_th:  float = Field(8.4,   description="Débit hydraulique V3 (T/h) = ~7%")

    # ── Rendement et état ──
    efficiency: float = Field(..., description="Rendement thermodynamique (%)")
    status:     StatusEnum = StatusEnum.NORMAL
    scenario:   Optional[str] = None

    # ── Contrôle Commande (renseigné sur params_sim uniquement) ──
    control_mode:        str            = Field("MANUAL", description="Mode opérateur: MANUAL | AUTO")
    machine_state:       str            = Field("GRID_CONNECTED", description="État machine: STOPPED|ROLLING|SYNCHRONIZING|GRID_CONNECTED|TRIPPED")
    setpoint_power_mw:   Optional[float] = Field(None,    description="Consigne puissance active (MW)")
    pid_kp:              Optional[float] = Field(None,    description="Gain PID proportionnel")
    pid_ki:              Optional[float] = Field(None,    description="Gain PID intégral")
    pid_kd:              Optional[float] = Field(None,    description="Gain PID dérivé")
    pid_error:           Optional[float] = Field(None,    description="Erreur PID courante (MW)")
    pid_output:          Optional[float] = Field(None,    description="Sortie PID (% V1 target)")
    sequence_state:      str            = Field("IDLE",   description="État séquence: IDLE|STARTING|STOPPING|TRIPPED")
    sequence_progress:   Optional[float] = Field(None,   description="Progression séquence (0..1)")
    tripped:             bool           = Field(False,    description="Arrêt d'urgence actif")
    interlock_warnings:  list           = Field(default_factory=list, description="Avertissements interlocks actifs")

    # ── AVR / Excitation (renseigné sur params_sim uniquement) ──
    avr_mode:      str            = Field("VOLTAGE", description="Mode AVR: OFF|VOLTAGE|COSPHI|MANUAL")
    avr_setpoint:  Optional[float] = Field(None,    description="Consigne AVR (kV ou cos φ selon mode)")
    avr_e_fd_pu:   Optional[float] = Field(None,    description="Tension d'excitation E_fd (p.u.)")
    avr_saturated: Optional[bool]  = Field(None,    description="Saturation E_fd active")
    avr_k_a:       Optional[float] = Field(None,    description="Gain régulateur K_A")
    avr_t_a:       Optional[float] = Field(None,    description="Constante de temps T_A (s)")
    # Limiteurs OEL/UEL/SCL (Phase 1 — B.2)
    avr_oel_active: Optional[bool]  = Field(False, description="Limiteur sur-excitation actif")
    avr_uel_active: Optional[bool]  = Field(False, description="Limiteur sous-excitation actif")
    avr_scl_active: Optional[bool]  = Field(False, description="Limiteur courant stator actif")
    avr_i_stator_a: Optional[float] = Field(None,  description="Courant stator mesuré (A)")
    # Désurchauffeur (Phase 1 — B.3)
    attemp_enabled:       Optional[bool]  = Field(True,  description="Désurchauffeur actif")
    attemp_setpoint_c:    Optional[float] = Field(440.0, description="Consigne T° HP désurchauffeur (°C)")
    attemp_injection_pct: Optional[float] = Field(0.0,   description="% injection eau désurchauffe")
    # Condenseur (Phase 1 — B.4)
    condenser_enabled:          Optional[bool]  = Field(True,  description="Régulation condenseur active")
    condenser_level_pct:        Optional[float] = Field(50.0,  description="Niveau hotwell (%)")
    condenser_vacuum_mbar:      Optional[float] = Field(64.0,  description="Vide condenseur (mbar)")
    condenser_pump_pct:         Optional[float] = Field(50.0,  description="% commande pompe extraction")
    condenser_ejector_pct:      Optional[float] = Field(50.0,  description="% commande éjecteur vide")
    condenser_level_setpoint:   Optional[float] = Field(50.0,  description="Consigne niveau hotwell (%)")
    condenser_vacuum_setpoint:  Optional[float] = Field(64.0,  description="Consigne vide condenseur (mbar)")

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
    valve_bp: Optional[float] = Field(None, ge=0, le=100, description="Vanne sortie BP (%)")