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

    if controller.tripped or controller.machine_state == "STOPPED":
        raise HTTPException(
            status_code=400,
            detail="Scénario indisponible — la machine doit être en marche (hors STOPPED) et hors AU pour déclencher un scénario.",
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
