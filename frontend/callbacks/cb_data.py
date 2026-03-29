"""
callbacks/cb_data.py — Master Data Fetcher (WebSocket + Polling)
Version corrigée pour garantir l'affichage des graphiques :
- Les données NOMINALES (Dashboard) arrivent par WebSocket.
- Les données SIMULÉES (Sandbox) arrivent par Polling.
- L'HISTORIQUE est maintenu et TOUJOURS renvoyé pour éviter les graphiques vides.
"""
import json
import requests
from dash import Input, Output, State, no_update, callback_context
from config import BACKEND

# Session HTTP réutilisable
_session = requests.Session()
_session.headers.update({"Connection": "keep-alive"})
_last_timestamp = None

def register(app):

    @app.callback(
        Output("store-current-data",    "data"),
        Output("store-simulation-data", "data"),
        Output("store-history",         "data"),
        Input("ws-data", "message"),             # Source Nominal (WS)
        Input("interval-fast", "n_intervals"),   # Source Simulation (Polling)
        State("store-current-data", "data"),
        State("store-simulation-data", "data"),
        State("store-history", "data"),
        prevent_initial_call=True
    )
    def master_data_update(ws_msg, n_inv, current_nom, current_sim, history):
        """
        Callback central mettant à jour les 3 stores principaux.
        Garanti que l'historique n'est jamais 'perdu' lors d'une mise à jour de simulation.
        """
        global _last_timestamp
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        history = history or []

        # 1) MISE À JOUR NOMINALE (WebSocket) -> Pousse vers Dashboard + Historique
        if trigger_id == "ws-data":
            if not ws_msg or not ws_msg.get("data"):
                return no_update, no_update, no_update
            
            try:
                d_nom = json.loads(ws_msg["data"])
                
                # Mise à jour historique
                ts = d_nom.get("timestamp")
                if ts != _last_timestamp:
                    _last_timestamp = ts
                    history.append(d_nom)
                    history = history[-60:]

                # On renvoie : Nouveau Nominal, Simulation inchangée, Nouvel Historique
                return d_nom, no_update, history
            except:
                return no_update, no_update, no_update

        # 2) MISE À JOUR SIMULATION (Polling) -> Pousse vers Sandbox
        elif trigger_id == "interval-fast":
            try:
                r = _session.get(f"{BACKEND}/data/simulated", timeout=0.5)
                if r.status_code == 200:
                    d_sim = r.json()
                    # On renvoie : Nominal inchangé, Nouvelle Simulation, Historique inchangé
                    return no_update, d_sim, history 
            except:
                pass

        return no_update, no_update, no_update
