"""
callbacks/cb_simulation.py — Callbacks contrôle simulation
Mise à jour : 5 vannes (V1/V2/V3/MP/BP), 10 scénarios, affichage nouveaux paramètres.
"""
import requests
from dash import Input, Output, State, html, no_update
from datetime import datetime
from config import BACKEND
from components.gta_synoptic import create_gta_synoptic

_session = requests.Session()


def register(app):

    # ── Affichage valeurs sliders (5 vannes) ──────────────────────────
    @app.callback(
        Output("val-v1",  "children"),
        Output("val-v2",  "children"),
        Output("val-v3",  "children"),
        Output("val-mp",  "children"),
        Output("val-bp",  "children"),
        Input("slider-v1",  "value"),
        Input("slider-v2",  "value"),
        Input("slider-v3",  "value"),
        Input("slider-mp",  "value"),
        Input("slider-bp",  "value"),
    )
    def update_valve_displays(v1, v2, v3, vmp, vbp):
        return str(v1), str(v2), str(v3), str(vmp), str(vbp)

    # ── Appliquer les vannes ──────────────────────────────────────────
    @app.callback(
        Output("valve-feedback", "children"),
        Input("btn-apply-valves", "n_clicks"),
        State("slider-v1", "value"),
        State("slider-v2", "value"),
        State("slider-v3", "value"),
        State("slider-mp", "value"),
        State("slider-bp", "value"),
        prevent_initial_call=True,
    )
    def apply_valves(_, v1, v2, v3, vmp, vbp):
        try:
            _session.post(
                f"{BACKEND}/simulation/valves",
                json={"valve_v1": v1, "valve_v2": v2, "valve_v3": v3,
                      "valve_mp": vmp, "valve_bp": vbp},
                timeout=2,
            )
            ts = datetime.now().strftime("%H:%M:%S")
            return (f"[{ts}] Vannes appliquées — "
                    f"V1:{v1}%  V2:{v2}%  V3:{v3}%  MP:{vmp}%  BP:{vbp}%")
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
            _session.post(f"{BACKEND}/simulation/reset",
                          json={"confirm": True}, timeout=2)
            ts = datetime.now().strftime("%H:%M:%S")
            return f"[{ts}] Système réinitialisé à l'état nominal"
        except Exception as e:
            return f"Erreur reset : {e}"

    # ── 10 Scénarios ──────────────────────────────────────────────────
    for sid in range(1, 11):
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
                ts   = datetime.now().strftime("%H:%M:%S")
                return f"[{ts}] Scénario déclenché : {name}"
            except Exception as e:
                return f"Erreur scénario : {e}"

    # ── Arrêter le scénario ───────────────────────────────────────────
    @app.callback(
        Output("scenario-feedback", "children", allow_duplicate=True),
        Input("btn-stop-scenario", "n_clicks"),
        prevent_initial_call=True,
    )
    def stop_scenario(_):
        try:
            _session.post(f"{BACKEND}/simulation/stop", timeout=2)
            ts = datetime.now().strftime("%H:%M:%S")
            return f"[{ts}] Scénario arrêté manuellement"
        except Exception as e:
            return f"Erreur arrêt : {e}"

    # ── Synoptique + panneau état ─────────────────────────────────────
    @app.callback(
        Output("sim-state-panel",  "children"),
        Output("gta-synoptic-sim", "children"),
        Output("btn-stop-scenario","style"),
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
        s_color = {"NORMAL": "#10b981", "DEGRADED": "#f59e0b",
                   "CRITICAL": "#ef4444"}.get(status, "#10b981")

        # Affichage des 5 vannes
        valve_rows = []
        valves = [
            ("V1", "valve_v1",  "#f97316", "Adm. HP"),
            ("V2", "valve_v2",  "#60a5fa", "Équil."),
            ("V3", "valve_v3",  "#60a5fa", "Équil."),
            ("MP", "valve_mp",  "#a78bfa", "Extr. MP"),
            ("BP", "valve_bp",  "#38bdf8", "Cond."),
        ]
        for name, key, col, desc in valves:
            val = d.get(key, 0)
            color = col if val > 30 else "#ef4444"
            valve_rows.append(html.Div([
                html.Span(f"{name}:", style={"color": "#475569", "width": "28px",
                                             "display": "inline-block"}),
                html.Span(f"{val:.0f}%", style={"color": color, "fontWeight": "700",
                                                  "width": "38px", "display": "inline-block"}),
                html.Span(desc, style={"color": "#334155", "fontSize": "10px"}),
            ], style={"fontFamily": "Share Tech Mono", "fontSize": "12px",
                      "marginBottom": "3px"}))

        # Paramètres clés
        params_grid = html.Div([
            html.Div([
                html.Span("P active: ", style={"color": "#475569"}),
                html.Span(f"{d.get('active_power',0):.1f} MW",
                          style={"color": "#10b981", "fontWeight": "700"}),
            ], style={"fontFamily": "Share Tech Mono", "fontSize": "12px"}),
            html.Div([
                html.Span("Vitesse: ", style={"color": "#475569"}),
                html.Span(f"{d.get('turbine_speed',0):.0f} RPM",
                          style={"color": "#60a5fa", "fontWeight": "700"}),
            ], style={"fontFamily": "Share Tech Mono", "fontSize": "12px"}),
            html.Div([
                html.Span("Rendement: ", style={"color": "#475569"}),
                html.Span(f"{d.get('efficiency',0):.1f}%",
                          style={"color": "#38bdf8", "fontWeight": "700"}),
            ], style={"fontFamily": "Share Tech Mono", "fontSize": "12px"}),
            html.Div([
                html.Span("P barillet: ", style={"color": "#475569"}),
                html.Span(
                    f"{d.get('pressure_bp_barillet',3.0):.2f} bar",
                    style={"color": "#ef4444" if d.get("pressure_bp_barillet",3.0) > 3.5
                           else "#a78bfa", "fontWeight": "700"},
                ),
            ], style={"fontFamily": "Share Tech Mono", "fontSize": "12px"}),
        ], style={"marginTop": "8px", "display": "grid",
                  "gridTemplateColumns": "1fr 1fr", "gap": "4px"})

        state_panel = html.Div([
            html.Div([
                html.Span("Statut : ", style={"color": "#475569"}),
                html.Span(status, style={"color": s_color, "fontWeight": "700"}),
            ], style={"fontFamily": "Share Tech Mono", "fontSize": "13px",
                      "marginBottom": "8px"}),
            html.Div([
                html.Span("Scénario : ", style={"color": "#475569"}),
                html.Span(d.get("scenario") or "Nominal",
                          style={"color": "#818cf8"}),
            ], style={"fontFamily": "Share Tech Mono", "fontSize": "12px",
                      "marginBottom": "10px"}),
            html.Div("Vannes", style={"color": "#334155", "fontSize": "10px",
                                      "marginBottom": "4px", "letterSpacing": "1px"}),
            html.Div(valve_rows),
            params_grid,
        ])

        has_scenario = d.get("scenario") is not None
        stop_style = ({"marginTop": "14px", "width": "100%", "display": "block"}
                      if has_scenario else {"display": "none"})

        return state_panel, synoptic_view, stop_style

    # ── Historique des scénarios ──────────────────────────────────────
    @app.callback(
        Output("scenario-history-list", "children"),
        Input("interval-slow", "n_intervals"),
        Input("url", "pathname"),
    )
    def update_history(_, pathname):
        if pathname != "/simulation":
            return no_update
        try:
            r = _session.get(f"{BACKEND}/simulation/history", timeout=1)
            if r.status_code == 200:
                items = [
                    html.Div([
                        html.Span(f"[{item['timestamp']}] ",
                                  style={"color": "#334155", "fontSize": "10px",
                                         "fontFamily": "Share Tech Mono"}),
                        html.Span(item["name"],
                                  style={"color": "#818cf8", "fontSize": "11px",
                                         "fontFamily": "Share Tech Mono"}),
                    ], style={"marginBottom": "4px"})
                    for item in reversed(r.json())
                ]
                return items or html.Div("Aucun scénario",
                                         style={"color": "#334155", "fontSize": "11px"})
        except Exception:
            pass
        return html.Div("Erreur historique", style={"color": "#ef4444"})