"""
callbacks/cb_settings.py — Callbacks page Paramètres
"""
import dash
import requests
from dash import Input, Output, State, html, no_update
from datetime import datetime
from config import BACKEND

THRESHOLD_PARAMS = [
    "pressure_hp", "temperature_hp", "steam_flow_hp",
    "turbine_speed", "active_power", "power_factor", "efficiency"
]


from layouts.settings import threshold_row

# Configuration des paramètres (déplacé ici pour accès global)
PARAMS_META = {
    "pressure_hp":    ("Pression HP", "bar"),
    "temperature_hp": ("Température HP", "°C"),
    "steam_flow_hp":  ("Débit vapeur HP", "T/h"),
    "turbine_speed":  ("Vitesse turbine", "RPM"),
    "active_power":   ("Puissance active", "MW"),
    "power_factor":   ("Facteur cosφ", "—"),
    "efficiency":     ("Rendement", "%"),
}


def register(app):

    @app.callback(
        Output("thresholds-rows-container", "children"),
        Input("url", "pathname"),
    )
    def load_thresholds_on_page_load(pathname):
        if pathname != "/settings":
            return no_update
            
        try:
            r = requests.get(f"{BACKEND}/settings/thresholds", timeout=3)
            thresholds = r.json() if r.status_code == 200 else {}
            
            rows = []
            for param, (label, unit) in PARAMS_META.items():
                val = thresholds.get(param, {"min": 0, "max": 100})
                rows.append(threshold_row(label, param, val["min"], val["max"], unit))
            return rows
        except Exception as e:
            print(f"Erreur chargement seuils: {e}")
            return html.Div("Erreur de connexion au serveur", 
                            style={"color": "#ef4444", "padding": "20px"})

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