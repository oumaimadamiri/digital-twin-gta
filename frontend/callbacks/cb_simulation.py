"""
callbacks/cb_simulation.py — Callbacks contrôle simulation (vannes + scénarios)
Optimisé : prevent_initial_call sur update_sim_ui, session HTTP réutilisable.
"""
import requests
from dash import Input, Output, State, html, no_update
from datetime import datetime
from config import BACKEND
from components.gta_synoptic import create_gta_synoptic

# Session réutilisable pour les appels POST
_session = requests.Session()

def register(app):

    # ── Affichage valeurs sliders ─────────────────────────────────────
    @app.callback(
        Output("val-v1", "children"),
        Output("val-v2", "children"),
        Output("val-v3", "children"),
        Input("slider-v1", "value"),
        Input("slider-v2", "value"),
        Input("slider-v3", "value"),
    )
    def update_valve_displays(v1, v2, v3):
        return str(v1), str(v2), str(v3)

    # ── Appliquer les vannes ──────────────────────────────────────────
    @app.callback(
        Output("valve-feedback", "children"),
        Input("btn-apply-valves", "n_clicks"),
        State("slider-v1", "value"),
        State("slider-v2", "value"),
        State("slider-v3", "value"),
        prevent_initial_call=True,
    )
    def apply_valves(_, v1, v2, v3):
        try:
            _session.post(
                f"{BACKEND}/simulation/valves",
                json={"valve_v1": v1, "valve_v2": v2, "valve_v3": v3},
                timeout=2,
            )
            ts = datetime.now().strftime("%H:%M:%S")
            return f"[{ts}] Vannes appliquées — V1:{v1}%  V2:{v2}%  V3:{v3}%"
        except Exception as e:
            return f"Erreur : {e}"

    # ── Reset nominal ─────────────────────────────────────────────────
    @app.callback(
        Output("valve-feedback", "children", allow_duplicate=True),
        Input("btn-reset", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_system(_):
        try:
            _session.post(f"{BACKEND}/simulation/reset", json={"confirm": True}, timeout=2)
            ts = datetime.now().strftime("%H:%M:%S")
            return f"[{ts}] Systeme reinitialise a l'etat nominal"
        except Exception as e:
            return f"Erreur reset : {e}"

    # ── Scénarios (7 boutons) ─────────────────────────────────────────
    for sid in range(1, 8):
        @app.callback(
            Output("scenario-feedback", "children", allow_duplicate=True),
            Input(f"btn-scenario-{sid}", "n_clicks"),
            prevent_initial_call=True,
        )
        def trigger_scenario(_, scenario_id=sid):
            try:
                r = _session.post(
                    f"{BACKEND}/simulation/scenario",
                    json={"scenario_id": scenario_id},
                    timeout=2,
                )
                data = r.json()
                name = data.get("scenario", {}).get("name", f"#{scenario_id}")
                ts = datetime.now().strftime("%H:%M:%S")
                return f"[{ts}] Scenario declenche : {name}"
            except Exception as e:
                return f"Erreur scenario : {e}"

    # ── Arrêter le scénario ──────────────────────────────────────────
    @app.callback(
        Output("scenario-feedback", "children", allow_duplicate=True),
        Input("btn-stop-scenario", "n_clicks"),
        prevent_initial_call=True,
    )
    def stop_scenario(_):
        try:
            _session.post(f"{BACKEND}/simulation/stop", timeout=2)
            ts = datetime.now().strftime("%H:%M:%S")
            return f"[{ts}] Scénario arrêté manuellment"
        except Exception as e:
            return f"Erreur arrêt : {e}"

    # ── Synoptique + panneau état de simulation ───────────────────────
    @app.callback(
        Output("sim-state-panel", "children"),
        Output("gta-synoptic-sim", "children"),
        Output("btn-stop-scenario", "style"),
        Input("store-simulation-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_sim_ui(d, pathname):
        if pathname != "/simulation":
            return no_update, no_update, no_update
        d = d or {}

        synoptic_view = create_gta_synoptic(d)

        status  = d.get("status", "NORMAL")
        s_color = {
            "NORMAL":   "#00e676",
            "DEGRADED": "#ffd740",
            "CRITICAL": "#ff3d57",
        }.get(status, "#00e676")

        valve_items = []
        for v_id in ["v1", "v2", "v3"]:
            key = f"valve_{v_id}"
            val = d.get(key, 0)
            color = "#00b4ff" if val > 50 else "#ffd740"
            valve_items.append(
                html.Div([
                    html.Span(f"{v_id.upper()}: ", style={"color": "#3a5a7a"}),
                    html.Span(f"{val:.0f}%",      style={"color": color}),
                ], style={"display": "inline-block", "marginRight": "16px",
                          "fontFamily": "Share Tech Mono", "fontSize": "12px"})
            )

        state_panel = html.Div([
            html.Div([
                html.Span("Statut : ", style={"color": "var(--text3)"}),
                html.Span(status, style={"color": s_color, "fontWeight": "700"}),
            ], style={"marginBottom": "8px", "fontFamily": "var(--mono)", "fontSize": "13px"}),

            html.Div([
                html.Span("Scénario : ", style={"color": "var(--text3)"}),
                html.Span(d.get("scenario") or "Nominal", style={"color": "var(--blue-bright)"}),
            ], style={"marginBottom": "8px", "fontFamily": "var(--mono)", "fontSize": "12px"}),

            html.Div(valve_items),
        ])

        # Affichage du bouton STOP si un scénario est en cours
        has_scenario = d.get("scenario") is not None
        stop_btn_style = {"marginTop": "16px", "width": "100%", "display": "block"} if has_scenario else {"display": "none"}

        return state_panel, synoptic_view, stop_btn_style

    # ── Historique des scénarios — Séparé pour la performance ─────────
    @app.callback(
        Output("scenario-history-list", "children"),
        Input("interval-slow", "n_intervals"),
        Input("url", "pathname"),
    )
    def update_history(_, pathname):
        if pathname != "/simulation":
            return no_update

        history_items = []
        try:
            r = _session.get(f"{BACKEND}/simulation/history", timeout=1)
            if r.status_code == 200:
                history = r.json()
                for item in reversed(history):
                    history_items.append(html.Div([
                        html.Span(f"[{item['timestamp']}] ", className="history-ts"),
                        html.Span(item['name'], className="history-name"),
                    ], className="history-item"))
            if not history_items:
                history_items = html.Div("Aucun scénario effectué", style={"color": "var(--text3)", "fontSize": "11px"})
        except:
            history_items = html.Div("Erreur historique", style={"color": "var(--red)"})

        return history_items
