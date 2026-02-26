"""
callbacks/cb_data.py — Gestion globale des données (Master Fetch)
Optimisé : session requests réutilisable, prevent_initial_call, skip si data inchangée.
"""
import requests
from dash import Input, Output, State, no_update
from config import BACKEND

# Session HTTP réutilisable (connexion persistante, ~3x plus rapide)
_session = requests.Session()
_session.headers.update({"Connection": "keep-alive"})
_last_timestamp = None

def register(app):

    @app.callback(
        Output("store-current-data", "data"),
        Output("store-simulation-data", "data"),
        Output("store-history", "data"),
        Input("interval-fast", "n_intervals"),
        State("store-history", "data"),
        prevent_initial_call=True,
    )
    def fetch_current_data(_, history):
        global _last_timestamp

        # 1. Fetch Nominal Data (for Dashboard)
        try:
            r_nom = _session.get(f"{BACKEND}/data/current", timeout=1)
            d_nom = r_nom.json()
        except Exception:
            d_nom = {}

        # 2. Fetch Simulated Data (for Simulation Page) — même session
        try:
            r_sim = _session.get(f"{BACKEND}/data/simulated", timeout=1)
            d_sim = r_sim.json()
        except Exception:
            d_sim = {}

        # 3. Mise à jour historique uniquement si nouveau timestamp
        history = history or []
        if d_nom:
            ts = d_nom.get("timestamp")
            if ts != _last_timestamp:
                _last_timestamp = ts
                history.append(d_nom)
                history = history[-60:]  # garder les 60 derniers points

        return d_nom, d_sim, history
