"""
callbacks/cb_simulation.py — Callbacks contrôle simulation

CORRECTIONS :
  1. Nouveau callback update_scenarios_list : charge les scénarios
     immédiatement sur changement de pathname (plus d'attente 5s)
     → résout la race condition "Chargement des scénarios..."
  2. Les scénarios sont triés par criticité (CRITIQUE en premier)
  3. trigger_dynamic_scenario : inchangé
"""
import dash
import requests
from dash import Input, Output, State, html, no_update, ctx
from datetime import datetime
from config import BACKEND
from components.gta_synoptic import create_gta_synoptic
from layouts.simulation import scenario_card, _CRITICITE

_session = requests.Session()

# Ordre de tri pour l'affichage des scénarios
_CRIT_ORDER = {"CRITIQUE": 0, "MAJEUR": 1, "MODÉRÉ": 2}

def _make_toggle(app, toggle_id, collapse_id):
    @app.callback(
        Output(collapse_id, "style"),
        Output(toggle_id, "children"),
        Input(f"{toggle_id}-btn", "n_clicks"),
        State(collapse_id, "style"),
        prevent_initial_call=True,
    )
    def toggle(n, current_style):
        is_open = (current_style or {}).get("display") != "none"
        if is_open:
            return {"display": "none"}, "▼"
        else:
            return {"display": "block"}, "▲"
        
def register(app):
    _make_toggle(app, "toggle-valves",    "collapse-valves")
    _make_toggle(app, "toggle-scenarios", "collapse-scenarios")
    _make_toggle(app, "toggle-history",   "collapse-history")
    # ── Affichage valeurs sliders ────────────────────────────────────
    @app.callback(
        Output("val-v1", "children"),
        Output("val-v2", "children"),
        Output("val-v3", "children"),
        Output("val-mp", "children"),
        Output("val-bp", "children"),
        Input("slider-v1", "value"),
        Input("slider-v2", "value"),
        Input("slider-v3", "value"),
        Input("slider-mp", "value"),
        Input("slider-bp", "value"),
    )
    def update_valve_displays(v1, v2, v3, vmp, vbp):
        return str(v1), str(v2), str(v3), str(vmp), str(vbp)

    # ── FIX : chargement scénarios sur URL change (plus de race condition) ──
    @app.callback(
        Output("scenarios-list-container", "children"),
        Input("url", "pathname"),
    )
    def update_scenarios_list(pathname):
        """
        Chargement immédiat des scénarios à l'arrivée sur /simulation.
        Remplace le chargement différé sur interval-slow (délai 5s).
        Les scénarios sont triés par criticité : CRITIQUE → MAJEUR → MODÉRÉ.
        """
        if pathname != "/simulation":
            return no_update
        try:
            r = _session.get(f"{BACKEND}/simulation/scenarios", timeout=2)
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")
            scenarios = r.json()

            # Tri par criticité
            def sort_key(s):
                sid = s.get("id", 99)
                crit_label = _CRITICITE.get(sid, ("MODÉRÉ", ""))[0]
                return _CRIT_ORDER.get(crit_label, 2)

            scenarios_sorted = sorted(scenarios, key=sort_key)

            return [scenario_card(s) for s in scenarios_sorted]

        except Exception as e:
            return html.Div(
                f"Erreur de chargement : {e}",
                style={"color": "#ef4444", "fontFamily": "Share Tech Mono",
                       "fontSize": "11px", "padding": "16px"},
            )

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

    # ── Déclenchement scénario (Pattern Matching) ─────────────────────
    @app.callback(
        Output("scenario-feedback", "children", allow_duplicate=True),
        Input({"type": "btn-scenario", "index": dash.ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def trigger_dynamic_scenario(n_clicks_list):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update

        triggered_id = ctx.triggered_id
        if not isinstance(triggered_id, dict) or "index" not in triggered_id:
            return no_update

        scenario_id = triggered_id["index"]
        clicked_value = next(
            (v for item, v in zip(ctx.inputs_list[0], n_clicks_list)
             if item["id"].get("index") == scenario_id),
            None,
        )
        if not clicked_value:
            return no_update

        try:
            r = _session.post(
                f"{BACKEND}/simulation/scenario",
                json={"scenario_id": scenario_id},
                timeout=2,
            )
            data = r.json()
            name = data.get("scenario", {}).get("name", f"#{scenario_id}")
            ts = datetime.now().strftime("%H:%M:%S")
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

    # ── Boutons scénarios dynamiques (Pattern Matching) ───────────────
    @app.callback(
        Output({"type": "btn-scenario", "index": dash.ALL}, "children"),
        Output({"type": "btn-scenario", "index": dash.ALL}, "className"),
        Output({"type": "btn-scenario", "index": dash.ALL}, "disabled"),
        Input("store-simulation-data", "data"),
        State({"type": "btn-scenario", "index": dash.ALL}, "value"),
        prevent_initial_call=True,
    )
    def update_scenario_buttons(d, btn_names):
        if not btn_names:
            return dash.no_update
        
        d = d or {}
        active_name = d.get("scenario")
        
        children = []
        classes = []
        disabled_list = []
        
        for name in btn_names:
            if not active_name:
                children.append("▶ DÉCLENCHER")
                classes.append("btn btn-scenario")
                disabled_list.append(False)
            elif name == active_name:
                children.append("🛑 EN COURS...")
                classes.append("btn btn-scenario active-scenario-btn")
                disabled_list.append(True)
            else:
                children.append("▶ DÉCLENCHER")
                classes.append("btn btn-scenario disabled-scenario-btn")
                disabled_list.append(True)
                
        return children, classes, disabled_list

    # ── Synoptique + panneau état ─────────────────────────────────────
    # ── NOUVEAU : patch JS du synoptique simulation (même logique que Dashboard) ──
    app.clientside_callback(
        """function(data, pathname) {
            if (pathname !== '/simulation') return window.dash_clientside.no_update;
            if (!data || Object.keys(data).length === 0)
                return window.dash_clientside.no_update;
            if (typeof window.patchGtaSynoptic === 'function')
                window.patchGtaSynoptic(data);
            return window.dash_clientside.no_update;
        }""",
        Output("syn-sim-patch-tick", "data"),
        Input("store-simulation-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )

    # ── MODIFIÉ : update_sim_ui ne reconstruit plus le SVG ──
    @app.callback(
        Output("sim-state-panel",   "children"),
        Output("btn-stop-scenario", "style"),
        # Output("gta-synoptic-sim", "children"),  ← SUPPRIMÉ
        Input("store-simulation-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_sim_ui(d, pathname):
        if pathname != "/simulation":
            return no_update, no_update  # 2 outputs au lieu de 3
        d = d or {}

        # synoptic_view = create_gta_synoptic(d)  ← SUPPRIMÉ
        status  = d.get("status", "NORMAL")
        s_color = {"NORMAL": "#10b981", "DEGRADED": "#f59e0b",
                   "CRITICAL": "#ef4444"}.get(status, "#10b981")

        valves = [
            ("V1", "valve_v1", "#f97316", "Adm. HP"),
            ("V2", "valve_v2", "#60a5fa", "Équil."),
            ("V3", "valve_v3", "#60a5fa", "Équil."),
            ("MP", "valve_mp", "#a78bfa", "Extr. MP"),
            ("BP", "valve_bp", "#38bdf8", "Cond."),
        ]
        
        state_panel = html.Div([
            # Deux colonnes
            html.Div([

                # ── Colonne gauche : statut + vannes ──
                html.Div([
                    html.Div([
                        html.Span("Statut: ", style={"color": "#475569"}),
                        html.Span(status, style={"color": s_color, "fontWeight": "700"}),
                    ], style={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                            "height": "22px", "display": "flex", "alignItems": "center",
                            "marginBottom": "6px"}),
                    html.Hr(style={"borderColor": "#2c5ea0", "margin": "10px 5"}),
                    
                    *[html.Div([
                        html.Span(f"{name}:", style={"color": "#475569", "width": "28px",
                                                    "display": "inline-block"}),
                        html.Span(f"{d.get(key, 0):.0f}%", style={
                            "color": col if d.get(key, 0) > 30 else "#ef4444",
                            "fontWeight": "700",
                        }),
                    ], style={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                            "height": "22px", "display": "flex", "alignItems": "center"})
                    for name, key, col in [
                        ("V1", "valve_v1", "#f97316"),
                        ("V2", "valve_v2", "#60a5fa"),
                        ("V3", "valve_v3", "#60a5fa"),
                        ("MP", "valve_mp", "#a78bfa"),
                        ("BP", "valve_bp", "#38bdf8"),
                    ]],
                ]),

                # ── Colonne droite : scénario + params ──
                html.Div([
                    html.Div([
                        html.Span("Scénario: ", style={"color": "#475569", "flexShrink": "0"}),
                        html.Span(d.get("scenario") or "Nominal",
                                style={
                                    "color": "#818cf8", "fontWeight": "700",
                                    "whiteSpace": "normal", "wordBreak": "break-word",
                                    "lineHeight": "1.3",
                                }),
                    ], style={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                            "height": "22px", "display": "flex", "alignItems": "flex-start",
                            "marginBottom": "6px"}),
                    html.Hr(style={"borderColor": "#2c5ea0", "margin": "10px 5"}),

                    *[html.Div([
                        html.Span(f"{label}:", style={"color": "#475569", "width": "60px",
                                                    "display": "inline-block"}),
                        html.Span(val, style={"color": col, "fontWeight": "700"}),
                    ], style={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                            "height": "22px", "display": "flex", "alignItems": "center"})
                    for label, val, col in [
                        ("P active",   f"{d.get('active_power', 0):.1f} MW",   "#10b981"),
                        ("Vitesse",    f"{d.get('turbine_speed', 0):.0f} RPM", "#60a5fa"),
                        ("Rendement",  f"{d.get('efficiency', 0):.1f} %",      "#38bdf8"),
                        ("P barillet", f"{d.get('pressure_bp_barillet', 3.0):.2f} bar",
                                    "#ef4444" if d.get("pressure_bp_barillet", 3.0) > 3.5 else "#a78bfa"),
                        ("cos φ",      f"{d.get('power_factor', 0):.3f}",      "#fbbf24"),
                    ]],
                ]),

            ], style={"display": "flex", "gap": "16px", "minWidth": "0"}),
        ])

        has_scenario = d.get("scenario") is not None
        stop_style = ({"marginTop": "14px", "width": "100%", "display": "block"}
                      if has_scenario else {"display": "none"})

        return state_panel, stop_style  # ← 2 valeurs au lieu de 3

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
                return items or html.Div("Aucun scénario déclenché",
                                         style={"color": "#334155", "fontSize": "11px"})
        except Exception:
            pass
        return html.Div("Erreur historique", style={"color": "#ef4444"})