"""
api/routes_simulation.py — Endpoints de contrôle de la simulation
"""

from fastapi import APIRouter, HTTPException
from models.scenario import ScenarioTrigger, ResetCommand
from models.gta_parameters import ValveCommand
from simulation.fake_api import fake_api
from simulation.scenarios import get_all_scenarios, get_scenario

import logging

logger = logging.getLogger("gta.api.simulation")

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.get("/scenarios")
def list_scenarios():
    """Retourne la liste des 10 scénarios disponibles."""
    return get_all_scenarios()


@router.post("/scenario")
def trigger_scenario(body: ScenarioTrigger):
    """Active un scénario de perturbation par son ID."""
    scenario = get_scenario(body.scenario_id)
    if scenario is None:
        logger.error(f"Tentative de déclenchement d'un scénario invalide : {body.scenario_id}")
        raise HTTPException(status_code=404, detail=f"Scénario {body.scenario_id} introuvable")
    
    logger.info(f"ACTION OPÉRATEUR : Déclenchement scénario '{scenario.name}' (ID: {body.scenario_id})")
    fake_api.trigger_scenario(body.scenario_id)
    return {
        "status":  "triggered",
        "scenario": {"id": scenario.id, "name": scenario.name},
    }


@router.post("/stop")
def stop_scenario():
    """Arrête le scénario en cours."""
    logger.info("ACTION OPÉRATEUR : Arrêt du scénario en cours")
    fake_api.stop_scenario()
    return {"status": "stopped", "message": "Scénario arrêté"}


@router.get("/history")
def get_scenario_history():
    """Retourne l'historique des scénarios déclenchés."""
    return fake_api._scenario_history


@router.post("/reset")
def reset_simulation(_: ResetCommand = None):
    """Réinitialise le GTA à l'état nominal et efface les alertes actives."""
    from services.alert_manager import alert_manager
    logger.info("ACTION OPÉRATEUR : Réinitialisation complète du système (RESET)")
    fake_api.reset()
    alert_manager.clear_alerts()
    return {"status": "reset", "message": "Système réinitialisé à l'état nominal"}


@router.post("/valves")
def set_valves(cmd: ValveCommand):
    """Modifie l'ouverture des 5 vannes V1, V2, V3, BP (0-100%)."""
    logger.info(
        f"ACTION OPÉRATEUR : Modification vannes -> "
        f"V1:{cmd.valve_v1}%, V2:{cmd.valve_v2}%, V3:{cmd.valve_v3}%, BP:{cmd.valve_bp}%"
    )
    fake_api.set_valves(
        v1=cmd.valve_v1, v2=cmd.valve_v2, v3=cmd.valve_v3,
        v_bp=cmd.valve_bp,
    )
    return {
        "status": "updated",
        "valves": {
            "v1": cmd.valve_v1, "v2": cmd.valve_v2, "v3": cmd.valve_v3,
            "bp": cmd.valve_bp,
        },
    }


@router.get("/state")
def get_simulation_state():
    """Retourne l'état courant de la simulation (scénario actif, statut)."""
    params = fake_api.get_current()
    if params is None:
        return {"status": "starting", "scenario": None}
    return {
        "status":   params.status,
        "scenario": params.scenario,
        "valves": {
            "v1": params.valve_v1,
            "v2": params.valve_v2,
            "v3": params.valve_v3,
            "bp": params.valve_bp,
        },
    }