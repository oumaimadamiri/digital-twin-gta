"""
api/routes_control.py — Endpoints Contrôle Commande GTA
Préfixe : /control
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query

from models.control import (
    ModeCommand, SetpointsCommand, PIDTuningCommand,
    SequenceCommand, EmergencyTripCommand, ValveControlCommand, ControlState,
    AVRModeCommand, AVRSetpointCommand, AVRGainsCommand, AVRManualCommand,
)
from simulation.controller import controller
from simulation.avr_controller import avr_controller
from simulation.valve_controller import valve_controller
from simulation.protection import protection_system
from services.data_manager import data_manager

router = APIRouter(prefix="/control", tags=["Contrôle Commande"])
logger = logging.getLogger("gta.control")


@router.get("/state", response_model=None)
def get_control_state():
    """Retourne l'état complet du superviseur Contrôle Commande."""
    return controller.get_state_dict()


@router.post("/mode")
def set_mode(cmd: ModeCommand):
    """Bascule le mode Manuel / Auto."""
    result = controller.set_mode(cmd.mode.value, operator=cmd.operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/setpoints")
def set_setpoints(cmd: SetpointsCommand):
    """Applique une nouvelle consigne de puissance (MW)."""
    sp = cmd.setpoints
    result = controller.set_setpoint(
        power_mw        = sp.power_mw,
        speed_rpm       = sp.speed_rpm,
        pressure_hp_bar = sp.pressure_hp_bar,
        operator        = cmd.operator,
    )
    return result


@router.post("/pid")
def tune_pid(cmd: PIDTuningCommand):
    """Règle les gains PID du régulateur de puissance."""
    result = controller.set_pid_gains(cmd.kp, cmd.ki, cmd.kd, operator=cmd.operator)
    return result


@router.post("/valve")
def manual_valve_override(cmd: ValveControlCommand):
    """
    Commande manuelle directe sur les vannes.
    Refusée si le mode est AUTO (basculer en MANUAL d'abord).
    """
    if controller.mode == "AUTO":
        raise HTTPException(
            status_code=400,
            detail="Commande manuelle refusée en mode AUTO. Basculez en MANUAL d'abord.",
        )

    positions_before = valve_controller.get_positions()
    results = {}
    for vid, val in [("v1", cmd.valve_v1), ("v2", cmd.valve_v2),
                     ("v3", cmd.valve_v3), ("bp", cmd.valve_bp)]:
        if val is not None:
            results[vid] = valve_controller.set_valve(vid, val)

    positions_after = valve_controller.get_positions()
    data_manager.log_operator_action(
        user=cmd.operator,
        action_type="VALVE_COMMAND",
        target="vannes",
        value_before=json.dumps(positions_before),
        value_after=json.dumps(positions_after),
        notes=json.dumps({k: v.get("message") for k, v in results.items() if not v.get("accepted")}),
    )
    return {"results": results, "valve_state": valve_controller.get_state()}


@router.post("/sequence/start")
def start_sequence(cmd: SequenceCommand):
    """Démarre une séquence start_turbine ou stop_turbine."""
    current_power = 0.0
    try:
        from simulation.fake_api import fake_api
        if fake_api.get_current():
            current_power = fake_api.get_current().active_power
    except Exception as e:
        logger.warning(f"fake_api.get_current() failed: {e}", exc_info=True)

    result = controller.start_sequence(
        name=cmd.sequence, operator=cmd.operator, current_power_mw=current_power
    )
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/sequence/stop")
def stop_sequence_route(cmd: SequenceCommand):
    """Lance la séquence d'arrêt normal (stop_turbine)."""
    current_power = 0.0
    try:
        from simulation.fake_api import fake_api
        if fake_api.get_current():
            current_power = fake_api.get_current().active_power
    except Exception as e:
        logger.warning(f"fake_api.get_current() failed: {e}", exc_info=True)

    result = controller.start_sequence(
        name="stop_turbine", operator=cmd.operator, current_power_mw=current_power
    )
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/sequence/cancel")
def cancel_sequence(operator: str = Query("Opérateur")):
    """Annule la séquence en cours."""
    result = controller.cancel_sequence(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/emergency/trip")
def emergency_trip(cmd: EmergencyTripCommand):
    """
    Arrêt d'urgence (AU / Trip) — ferme V1 instantanément.
    Le champ 'confirm' doit être True.
    """
    if not cmd.confirm:
        raise HTTPException(status_code=400, detail="Confirmation requise (confirm: true).")
    result = controller.emergency_trip(operator=cmd.operator)
    return result


@router.post("/emergency/reset")
def reset_trip(operator: str = Query("Opérateur")):
    """Réinitialise le trip après inspection. Permet de repasser en AUTO."""
    result = controller.reset_trip(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ── Protections automatiques ─────────────────────────────────────────────────

@router.get("/protections")
def get_protections():
    """Liste l'état de toutes les protections + historique des 50 derniers déclenchements."""
    return {
        "protections": protection_system.get_status(),
        "history":     protection_system.get_history(),
    }


@router.post("/protections/{name}/inhibit")
def inhibit_protection(name: str, inhibited: bool = True, operator: str = Query("Opérateur")):
    """Inhibe ou réarme une protection par nom (pour tests uniquement)."""
    result = protection_system.inhibit(name, inhibited)
    if not result.get("accepted"):
        raise HTTPException(status_code=404, detail=result["message"])
    data_manager.log_operator_action(
        user=operator, action_type="PROTECTION_INHIBIT",
        target=name, value_before=str(not inhibited), value_after=str(inhibited),
    )
    return result


# ── Couplage / Découplage réseau ─────────────────────────────────────────────

@router.post("/grid/synchronize")
def grid_synchronize(operator: str = Query("Opérateur")):
    """Couple la machine au réseau (SYNCHRONIZING → GRID_CONNECTED)."""
    result = controller.connect_to_grid(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/grid/disconnect")
def grid_disconnect(operator: str = Query("Opérateur")):
    """Découple la machine du réseau (GRID_CONNECTED → ROLLING)."""
    result = controller.disconnect_from_grid(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ── AVR / Excitation ──────────────────────────────────────────────────────────

@router.post("/avr/mode")
def set_avr_mode(cmd: AVRModeCommand):
    """Bascule le mode AVR : OFF / VOLTAGE / COSPHI / MANUAL."""
    result = avr_controller.set_mode(cmd.mode.value, operator=cmd.operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/avr/setpoint")
def set_avr_setpoint(cmd: AVRSetpointCommand):
    """Applique une nouvelle consigne tension (kV) ou cos φ."""
    result = avr_controller.set_setpoint(
        voltage_kv=cmd.voltage_kv,
        cosphi=cmd.cosphi,
        operator=cmd.operator,
    )
    return result


@router.post("/avr/gains")
def set_avr_gains(cmd: AVRGainsCommand):
    """Règle K_A et T_A du régulateur d'excitation."""
    result = avr_controller.set_gains(cmd.k_a, cmd.t_a, operator=cmd.operator)
    return result


@router.post("/avr/manual")
def set_avr_manual(cmd: AVRManualCommand):
    """Fixe E_fd directement en mode MANUAL."""
    result = avr_controller.set_e_fd_manual(cmd.e_fd_pu, operator=cmd.operator)
    return result
