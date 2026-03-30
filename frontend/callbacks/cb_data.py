"""
callbacks/cb_data.py — Master Data Fetcher (WebSocket + Polling)

CORRECTIONS :
  1. Race condition WS + polling : les deux triggers ne partagent plus
     le même Output "store-history". Le polling ne touche QUE store-simulation-data.
  2. Callback séparé pour la simulation (interval-fast) → plus de conflit.
  3. Guard sur ws_msg["data"] renforcée (KeyError possible).
  4. _last_timestamp déclaré proprement avec nonlocal.
"""
import json
import requests
from dash import Input, Output, State, no_update, callback_context
from config import BACKEND

_session = requests.Session()
_session.headers.update({"Connection": "keep-alive"})
_last_timestamp = None


def register(app):

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

        # Mise à jour historique (fenêtre glissante 60 points)
        history = list(history or [])
        history.append(d_nom)
        if len(history) > 60:
            history = history[-60:]

        return d_nom, history

    # ── Callback 2 : Polling → données simulées uniquement ───────────
    @app.callback(
        Output("store-simulation-data", "data"),
        Input("interval-fast", "n_intervals"),
        prevent_initial_call=True,
    )
    def update_simulation_from_poll(_):
        """
        Polling des données simulées (sandbox) toutes les secondes.
        ISOLÉ du callback WebSocket pour éviter toute race condition.
        """
        try:
            r = _session.get(f"{BACKEND}/data/simulated", timeout=0.8)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return no_update