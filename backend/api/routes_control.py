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
    RegulationTargetRequest,
    AttemperatorSetpointCommand, AttemperatorEnableCommand,
    CondLevelSetpointCommand, CondVacuumSetpointCommand,
)
from simulation.controller import controller
from simulation.avr_controller import avr_controller
from simulation.valve_controller import valve_controller
from simulation.protection import protection_system
from simulation.degradation import degradation
from simulation.attemperator import attemperator
from simulation.condenser import condenser
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
    """Règle les gains PID : power (défaut), speed ou pressure."""
    result = controller.set_pid_gains(cmd.kp, cmd.ki, cmd.kd,
                                      operator=cmd.operator, loop=cmd.loop)
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
                     ("v3", cmd.valve_v3), ("bp", cmd.valve_bp),
                     ("bp_admit", cmd.valve_bp_admit)]:
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


# ── Régulation cible (POWER / PRESSURE) ──────────────────────────────────────

@router.post("/regulation-target")
def set_regulation_target(req: RegulationTargetRequest):
    """Bascule entre régulation POWER (puissance → V1) et PRESSURE (pression HP → V1).
    Réservé à l'état GRID_CONNECTED."""
    result = controller.set_regulation_target(req.target.value, operator=req.operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=409, detail=result["message"])
    return result


# ── Dégradation Weibull ───────────────────────────────────────────────────────

@router.get("/degradation")
def get_degradation():
    """Retourne l'état courant du modèle de dégradation Weibull."""
    return degradation.snapshot()


@router.post("/degradation/reset")
def reset_degradation(operator: str = Query("Opérateur")):
    """Remet le compteur d'heures GRID à zéro (maintenance / test)."""
    return degradation.reset(operator=operator)


# ── Séquence de démarrage manuel (pas-à-pas) ─────────────────────────────────

@router.post("/startup/barrage")
def startup_open_barrage(operator: str = Query("Opérateur")):
    """Étape 2 : ouvre la vanne vapeur de barrage (bp_admit → 100%)."""
    result = controller.cmd_open_barrage(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/startup/v1")
def startup_open_v1(operator: str = Query("Opérateur")):
    """Étape 3 : ouvre V1 (interlock bp_admit ≥ 80%)."""
    result = controller.cmd_open_v1(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/startup/excite")
def startup_excite(operator: str = Query("Opérateur")):
    """Étape 5 : active l'AVR — excitation alternateur."""
    result = controller.cmd_excite(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/startup/sync-arm")
def startup_sync_arm(operator: str = Query("Opérateur")):
    """Étape 6 : arme la synchronisation réseau (ROLLING → SYNCHRONIZING)."""
    result = controller.cmd_synchronize_arm(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/startup/couple")
def startup_couple(operator: str = Query("Opérateur")):
    """Étape 7 : couplage réseau (SYNCHRONIZING → GRID_CONNECTED)."""
    result = controller.cmd_couple_grid(operator=operator)
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ── Couplage / Découplage réseau ──────────────────────────────────────────────

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


# ── Désurchauffeur (Phase 1 — B.3) ───────────────────────────────────────────

@router.get("/attemperator")
def get_attemperator():
    """Retourne l'état courant du désurchauffeur."""
    return attemperator.snapshot()


@router.post("/attemperator/setpoint")
def set_attemp_setpoint(cmd: AttemperatorSetpointCommand):
    """Fixe la consigne T° vapeur HP du désurchauffeur (°C)."""
    return attemperator.set_setpoint(cmd.setpoint_c, operator=cmd.operator)


@router.post("/attemperator/enabled")
def set_attemp_enabled(cmd: AttemperatorEnableCommand):
    """Active ou désactive le désurchauffeur."""
    return attemperator.set_enabled(cmd.enabled, operator=cmd.operator)


# ── Condenseur (Phase 1 — B.4) ────────────────────────────────────────────────

@router.get("/condenser")
def get_condenser():
    """Retourne l'état courant du condenseur."""
    return condenser.snapshot()


@router.post("/condenser/level-setpoint")
def set_cond_level_sp(cmd: CondLevelSetpointCommand):
    """Fixe la consigne niveau hotwell (%)."""
    return condenser.set_level_setpoint(cmd.setpoint_pct, operator=cmd.operator)


@router.post("/condenser/vacuum-setpoint")
def set_cond_vacuum_sp(cmd: CondVacuumSetpointCommand):
    """Fixe la consigne vide condenseur (mbar)."""
    return condenser.set_vacuum_setpoint(cmd.setpoint_mbar, operator=cmd.operator)
