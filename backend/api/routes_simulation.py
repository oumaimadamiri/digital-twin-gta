"""
api/routes_simulation.py — Endpoints de contrôle de la simulation
"""
import json as _json

from fastapi import APIRouter, HTTPException
from models.scenario import ScenarioTrigger, ResetCommand
from models.gta_parameters import ValveCommand
from simulation.fake_api import fake_api
from simulation.controller import controller
from simulation.scenarios import get_all_scenarios, get_scenario
from services.data_manager import data_manager
from models.scenario import ScenarioTrigger, ResetCommand, ESVCommand, LubricationOffsetCommand, SandboxCommand
from models.control import AVRModeCommand, AVRSetpointCommand, AVRManualCommand

import logging

logger = logging.getLogger("gta.api.simulation")

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.get("/scenarios")
def list_scenarios():
    """Retourne la liste des 10 scénarios disponibles."""
    return get_all_scenarios()


@router.post("/scenario")
def trigger_scenario(body: ScenarioTrigger, operator: str = "Opérateur"):
    """Active un scénario de perturbation par son ID."""
    scenario = get_scenario(body.scenario_id)
    if scenario is None:
        logger.error(f"Tentative de déclenchement d'un scénario invalide : {body.scenario_id}")
        raise HTTPException(status_code=404, detail=f"Scénario {body.scenario_id} introuvable")

    current     = fake_api.get_current()
    sim_state   = current.machine_state if current else controller.machine_state
    sim_tripped = current.tripped if current else controller.tripped

    if sim_tripped or sim_state != "GRID_CONNECTED":
        raise HTTPException(
            status_code=400,
            detail="Scénario indisponible — la machine doit être en marche (GRID_CONNECTED) et hors AU pour déclencher un scénario.",
        )

    fake_api.trigger_scenario(body.scenario_id)
    data_manager.log_operator_action(
        user=operator,
        action_type="SCENARIO_TRIGGER",
        target=f"scenario_{body.scenario_id}",
        value_before="aucun",
        value_after=scenario.name,
    )
    logger.info(f"ACTION OPÉRATEUR [{operator}]: Déclenchement scénario '{scenario.name}' (ID: {body.scenario_id})")
    return {
        "status":  "triggered",
        "scenario": {"id": scenario.id, "name": scenario.name},
    }


@router.post("/stop")
def stop_scenario(operator: str = "Opérateur"):
    """Arrête le scénario en cours."""
    current = fake_api.get_current()
    current_scenario = current.scenario if current else None
    fake_api.stop_scenario()
    data_manager.log_operator_action(
        user=operator,
        action_type="SCENARIO_STOP",
        target=f"scenario_{current_scenario}" if current_scenario else "aucun",
        value_before=current_scenario or "aucun",
        value_after="arrêté",
    )
    logger.info(f"ACTION OPÉRATEUR [{operator}]: Arrêt du scénario en cours")
    return {"status": "stopped", "message": "Scénario arrêté"}

@router.post("/reset-sim")
def reset_sim_machine(operator: str = "Opérateur"):
    """Réinitialise la machine simulée (efface un trip simulé) et re-synchronise sur la machine réelle."""
    fake_api.reset_sim_machine()
    data_manager.log_operator_action(
        user=operator, action_type="SIM_RESET",
        target="sim_machine", value_before="TRIPPED/forké", value_after="re-sync réel",
    )
    logger.info(f"ACTION OPÉRATEUR [{operator}]: Reset machine simulée")
    return {"status": "reset", "message": "Machine simulée réinitialisée"}

@router.post("/esv")
def set_sim_esv(body: ESVCommand):
    """Ouvre/ferme l'ESV — agit sur le fork simulé pendant un scénario, sur la machine réelle sinon."""
    result = fake_api.set_esv(body.open, operator=body.operator)
    data_manager.log_operator_action(
        user=body.operator, action_type="SIM_ESV",
        target="esv_sim",
        value_before=str(not body.open), value_after=str(body.open),
    )
    logger.info(f"ACTION OPÉRATEUR [{body.operator}]: ESV (simulation) → {'ouverte' if body.open else 'fermée'}")
    return result

@router.post("/sandbox")
def toggle_sandbox(body: SandboxCommand):
    """Active/désactive le bac à sable manuel (fork sans scénario — ESV/AVR/lubrification/vannes)."""
    result = fake_api.toggle_sandbox(body.active, operator=body.operator)
    data_manager.log_operator_action(
        user=body.operator, action_type="SIM_SANDBOX",
        target="sandbox_sim",
        value_before=str(not body.active), value_after=str(body.active),
    )
    logger.info(f"ACTION OPÉRATEUR [{body.operator}]: Bac à sable simulation → {'activé' if body.active else 'désactivé'}")
    return result

@router.post("/lubrication")
def set_sim_lubrication(body: LubricationOffsetCommand):
    """Offsets manuels pression/température huile — sandbox, scénario actif requis."""
    result = fake_api.set_lube_offsets(body.press_offset, body.temp_offset)
    if result.get("accepted"):
        data_manager.log_operator_action(
            user=body.operator, action_type="SIM_LUBE_OFFSET",
            target="lube_sim",
            value_before="0/0",
            value_after=f"{body.press_offset}/{body.temp_offset}",
        )
        logger.info(
            f"ACTION OPÉRATEUR [{body.operator}]: Offsets huile (simulation) → "
            f"ΔP={body.press_offset} bar, ΔT={body.temp_offset} °C"
        )
    return result

@router.post("/avr/mode")
def set_sim_avr_mode(body: AVRModeCommand):
    """Mode AVR de la machine simulée — sandbox, scénario actif requis."""
    return fake_api.set_avr_mode(body.mode.value, operator=body.operator)


@router.post("/avr/setpoint")
def set_sim_avr_setpoint(body: AVRSetpointCommand):
    """Consigne AVR (tension/cos φ) de la machine simulée — sandbox, scénario actif requis."""
    return fake_api.set_avr_setpoint(voltage_kv=body.voltage_kv, cosphi=body.cosphi, operator=body.operator)

@router.post("/avr/efd")
def set_sim_avr_efd(body: AVRManualCommand):
    """E_fd manuel AVR de la machine simulée — sandbox, scénario actif requis."""
    return fake_api.set_avr_efd_manual(body.e_fd_pu, operator=body.operator)

@router.post("/reset-controls")
def reset_sim_controls(operator: str = "Opérateur"):
    """Réinitialise ESV/AVR/lubrification du fork simulé (sandbox) à leurs valeurs nominales."""
    result = fake_api.reset_sim_controls(operator=operator)
    if result.get("accepted"):
        data_manager.log_operator_action(
            user=operator, action_type="SIM_CONTROLS_RESET",
            target="esv_avr_lube_sim", value_before="modifié", value_after="nominal",
        )
        logger.info(f"ACTION OPÉRATEUR [{operator}]: Reset ESV/AVR/Lubrification (sandbox) → nominal")
    return result

@router.get("/history")
def get_scenario_history():
    """Retourne l'historique des scénarios déclenchés."""
    return fake_api._scenario_history


@router.post("/reset")
def reset_simulation(_: ResetCommand = None, operator: str = "Opérateur"):
    """Réinitialise le GTA à l'état nominal et efface les alertes actives."""
    from services.alert_manager import alert_manager
    fake_api.reset()
    alert_manager.clear_alerts()
    data_manager.log_operator_action(
        user=operator,
        action_type="RESET",
        target="ALL",
        value_before="simulé",
        value_after="nominal",
    )
    logger.info(f"ACTION OPÉRATEUR [{operator}]: Réinitialisation complète du système (RESET)")
    return {"status": "reset", "message": "Système réinitialisé à l'état nominal"}


@router.post("/valves")
def set_valves(cmd: ValveCommand, operator: str = "Opérateur"):
    """Modifie l'ouverture des vannes V1, V2, V3, BP via le contrôleur d'actionneurs."""
    # Positions avant la commande
    before_state = fake_api.get_valve_positions()
    before_str = _json.dumps({k: round(v["current"], 1) for k, v in before_state.items()})

    # Délégation au contrôleur (rampe + vérification sécurité)
    results = fake_api.set_valves(v1=cmd.valve_v1, v2=cmd.valve_v2, v3=cmd.valve_v3, v_bp=cmd.valve_bp)

    after_str = _json.dumps({"v1": cmd.valve_v1, "v2": cmd.valve_v2,
                              "v3": cmd.valve_v3, "bp": cmd.valve_bp})
    # Refus éventuels du contrôleur (sécurité)
    rejections = {k: v["message"] for k, v in results.items() if not v.get("accepted", True)}
    notes = "; ".join(f"{k}: {m}" for k, m in rejections.items()) if rejections else None

    data_manager.log_operator_action(
        user=operator,
        action_type="VALVE_COMMAND",
        target="V1,V2,V3,BP",
        value_before=before_str,
        value_after=after_str,
        notes=notes,
    )
    logger.info(
        f"ACTION OPÉRATEUR [{operator}]: Vannes → "
        f"V1:{cmd.valve_v1}%  V2:{cmd.valve_v2}%  V3:{cmd.valve_v3}%  BP:{cmd.valve_bp}%"
        + (f" | REFUS: {notes}" if notes else "")
    )
    return {
        "status": "updated",
        "valves": {"v1": cmd.valve_v1, "v2": cmd.valve_v2,
                   "v3": cmd.valve_v3, "bp": cmd.valve_bp},
        "controller_results": results,
        "rejections": rejections,
    }


@router.get("/state")
def get_simulation_state():
    """Retourne l'état courant de la simulation (scénario actif, statut, vannes)."""
    params = fake_api.get_current()
    if params is None:
        return {"status": "starting", "scenario": None}
    valve_state = fake_api.get_valve_positions()
    return {
        "status":   params.status,
        "scenario": params.scenario,
        "valves":   valve_state,
    }
