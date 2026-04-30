"""
callbacks/cb_data.py — Master Data Fetcher (WebSocket + Polling)

CORRECTIONS :
  1. Race condition WS + polling : les deux triggers ne partagent plus
     le même Output "store-history".
  2. Callback séparé pour la simulation (interval-fast) → plus de conflit.
  3. Guard sur ws_msg["data"] renforcée (KeyError possible).
  4. _last_timestamp déclaré proprement avec nonlocal.
  5. [FIX-3]  Polling simulation court-circuité hors page /simulation
     → zéro requête HTTP parasite quand l'utilisateur est ailleurs.
  6. [FIX-4a] Fenêtre historique : 60 → 300 points (2m30s @ 500ms/push).
"""
import json
import requests
from dash import Input, Output, State, no_update
from config import BACKEND

_session = requests.Session()
_session.headers.update({"Connection": "keep-alive"})
_last_timestamp = None

_RT_FIELDS = frozenset([
    "timestamp", "active_power", "pressure_hp",
    "turbine_speed", "temperature_hp", "efficiency", "power_factor",
    # champs nécessaires aux KPIs et alertes (conservés en plus)
    "status", "turbine_speed", "current_a", "pressure_bp_barillet",
    "reactive_power", "apparent_power", "power_factor", "voltage",
    "steam_flow_hp", "pressure_bp_in", "steam_flow_condenser",
    # centrale huile lubrification (sparkline + historique analyse)
    "lube_oil_press", "lube_oil_temp", "lube_oil_temp_out",
    "lube_oil_tank_level", "lube_oil_filter_dp",
])

def register(app):

    # ── Activation/désactivation de interval-fast selon la page ──────
    @app.callback(
        Output("interval-fast", "disabled"),
        Input("url", "pathname"),
    )
    def toggle_interval_fast(pathname):
        """
        interval-fast (1s) sert uniquement au polling simulation sur /simulation.
        Il est désactivé sur toutes les autres pages pour économiser les cycles JS.
        Note : l'horloge (cb_dashboard) passe sur interval-slow (5s) hors /dashboard,
               ce qui est suffisant.
        """
        return pathname != "/simulation"
    
    # ── Callback 1 : WebSocket → données nominales + historique ──────
    @app.callback(
        Output("store-current-data", "data"),
        Output("store-history",      "data"),
        Input("ws-data", "message"),
        State("store-history", "data"),
        prevent_initial_call=True,
    )
    def update_nominal_from_ws(ws_msg, history):
        """
        Réception des données nominales via WebSocket (push ~500ms).
        MET À JOUR : store-current-data + store-history.
        NE TOUCHE PAS : store-simulation-data (callback séparé).
        """
        global _last_timestamp

        # Guard robuste : message absent ou mal formé
        if not ws_msg:
            return no_update, no_update
        raw = ws_msg.get("data") if isinstance(ws_msg, dict) else None
        if not raw:
            return no_update, no_update

        try:
            d_nom = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return no_update, no_update

        # Déduplication par timestamp
        ts = d_nom.get("timestamp")
        if ts and ts == _last_timestamp:
            return no_update, no_update
        _last_timestamp = ts

        # ── FIX : snapshot allégé pour l'historique ──────────────────
        slim = {k: v for k, v in d_nom.items() if k in _RT_FIELDS}

        # [FIX-4a] Fenêtre glissante portée à 300 points (2m30s @ 500ms/push)
        history = list(history or [])
        history.append(slim)
        if len(history) > 300:
            history = history[-300:]

        return d_nom, history

    # ── Callback 2 : Polling → données simulées uniquement ───────────
    # [FIX-3] State pathname ajouté : le polling est court-circuité si
    #          l'utilisateur n'est pas sur la page /simulation.
    #          Cela supprime toutes les requêtes HTTP parasites (~1/s)
    #          pendant la navigation sur Dashboard, Analyse, IA, Settings.
    @app.callback(
        Output("store-simulation-data", "data"),
        Input("interval-fast", "n_intervals"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_simulation_from_poll(_, pathname):
        """
        Polling des données simulées (sandbox) toutes les secondes.
        ISOLÉ du callback WebSocket pour éviter toute race condition.
        Désactivé hors page /simulation pour économiser la bande passante.
        """
        if pathname != "/simulation":
            return no_update
        try:
            r = _session.get(f"{BACKEND}/data/simulated", timeout=0.8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return no_update