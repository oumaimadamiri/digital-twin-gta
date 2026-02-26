"""
api/routes_simulation.py — Endpoints de contrôle de la simulation
"""

from fastapi import APIRouter, HTTPException
from models.scenario import ScenarioTrigger, ResetCommand
from models.gta_parameters import ValveCommand
from simulation.fake_api import fake_api
from simulation.scenarios import get_all_scenarios, get_scenario

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.get("/scenarios")
def list_scenarios():
    """Retourne la liste des 7 scénarios disponibles."""
    return get_all_scenarios()


@router.post("/scenario")
def trigger_scenario(body: ScenarioTrigger):
    """Active un scénario de perturbation par son ID."""
    scenario = get_scenario(body.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scénario {body.scenario_id} introuvable")
    fake_api.trigger_scenario(body.scenario_id)
    return {
        "status":  "triggered",
        "scenario": {"id": scenario.id, "name": scenario.name},
    }


@router.post("/reset")
def reset_simulation(_: ResetCommand = None):
    """Réinitialise le GTA à l'état nominal et efface les alertes actives."""
    from services.alert_manager import alert_manager
    fake_api.reset()
    alert_manager.clear_alerts()
    return {"status": "reset", "message": "Système réinitialisé à l'état nominal"}


@router.post("/valves")
def set_valves(cmd: ValveCommand):
    """Modifie l'ouverture des vannes V1, V2, V3 (0-100%)."""
    fake_api.set_valves(v1=cmd.valve_v1, v2=cmd.valve_v2, v3=cmd.valve_v3)
    return {
        "status": "updated",
        "valves": {
            "v1": cmd.valve_v1,
            "v2": cmd.valve_v2,
            "v3": cmd.valve_v3,
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
        },
    }