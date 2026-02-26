"""
callbacks/cb_settings.py — Callbacks page Paramètres
"""
import requests
from dash import Input, Output, State
from datetime import datetime
from config import BACKEND

THRESHOLD_PARAMS = [
    "pressure_hp", "temperature_hp", "steam_flow_hp",
    "turbine_speed", "active_power", "power_factor", "efficiency"
]


def register(app):

    @app.callback(
        Output("thresh-save-status", "children"),
        Input("btn-save-thresholds", "n_clicks"),
        *[State(f"thresh-{p}-min", "value") for p in THRESHOLD_PARAMS],
        *[State(f"thresh-{p}-max", "value") for p in THRESHOLD_PARAMS],
        prevent_initial_call=True,
    )
    def save_thresholds(_, *values):
        n = len(THRESHOLD_PARAMS)
        mins = values[:n]
        maxs = values[n:]
        thresholds = {
            param: {"min": float(mn or 0), "max": float(mx or 100)}
            for param, mn, mx in zip(THRESHOLD_PARAMS, mins, maxs)
        }
        try:
            requests.put(
                f"{BACKEND}/settings/thresholds",
                json={"thresholds": thresholds},
                timeout=2,
            )
            ts = datetime.now().strftime("%H:%M:%S")
            return f"✓ Seuils sauvegardés à {ts}"
        except Exception as e:
            return f"Erreur : {e}"