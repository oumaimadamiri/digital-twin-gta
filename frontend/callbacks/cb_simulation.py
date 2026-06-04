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

# Styles réutilisables pour l'accordéon
_WRAP_EXPANDED  = {"flex": "1",        "minWidth": "0",    "transition": "flex 0.25s ease"}
_WRAP_COLLAPSED = {"flex": "0 0 auto",  "minWidth": "auto", "transition": "flex 0.25s ease"}
_SHOW = {"display": "block"}
_HIDE = {"display": "none"}

def register(app):
    # ── Accordéon horizontal : 1 seul callback pour les 3 sections ──────────
    @app.callback(
        # Corps (show/hide)
        Output("collapse-valves",    "style"),
        Output("collapse-scenarios", "style"),
        Output("collapse-history",   "style"),
        # Flèches
        Output("toggle-valves",    "children"),
        Output("toggle-scenarios", "children"),
        Output("toggle-history",   "children"),
        # Wrappers flex
        Output("section-valves-wrap",    "style"),
        Output("section-scenarios-wrap", "style"),
        Output("section-history-wrap",   "style"),
        # Déclencheurs
        Input("toggle-valves-btn",    "n_clicks"),
        Input("toggle-scenarios-btn", "n_clicks"),
        Input("toggle-history-btn",   "n_clicks"),
        # État courant des corps
        State("collapse-valves",    "style"),
        State("collapse-scenarios", "style"),
        State("collapse-history",   "style"),
        prevent_initial_call=True,
    )
    def accordion_toggle(n_v, n_s, n_h, s_v, s_s, s_h):
        triggered = dash.callback_context.triggered_id

        # Quel panneau était ouvert ?
        was_open = {
            "toggle-valves-btn":    (s_v or {}).get("display") != "none",
            "toggle-scenarios-btn": (s_s or {}).get("display") != "none",
            "toggle-history-btn":   (s_h or {}).get("display") != "none",
        }
        keys = ["toggle-valves-btn", "toggle-scenarios-btn", "toggle-history-btn"]

        if triggered not in keys:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        # Comportement accordéon :
        # - si la section cliquée était OUVERTE → tout fermer
        # - sinon → ouvrir celle-ci, fermer les deux autres
        if was_open[triggered]:
            new_open = {k: False for k in keys}
        else:
            new_open = {k: (k == triggered) for k in keys}

        def body(k):    return _SHOW if new_open[k] else _HIDE
        def wrap(k):    return _WRAP_EXPANDED if new_open[k] else _WRAP_COLLAPSED
        def arrow(k):   return "▼" if new_open[k] else "▶"

        v, s, h = "toggle-valves-btn", "toggle-scenarios-btn", "toggle-history-btn"
        return (
            body(v), body(s), body(h),
            arrow(v), arrow(s), arrow(h),
            wrap(v), wrap(s), wrap(h),
        )
    # ── Affichage valeurs sliders ────────────────────────────────────
    @app.callback(
        Output("val-v1", "children"),
        Output("val-v2", "children"),
        Output("val-v3", "children"),
        Output("val-bp", "children"),
        Input("slider-v1", "value"),
        Input("slider-v2", "value"),
        Input("slider-v3", "value"),
        Input("slider-bp", "value"),
    )
    def update_valve_displays(v1, v2, v3, vbp):
        return str(v1), str(v2), str(v3), str(vbp)

    # ── Verrouillage des contrôles vannes sur AU ─────────────────────────
    @app.callback(
        Output("slider-v1",       "disabled"),
        Output("slider-v2",       "disabled"),
        Output("slider-v3",       "disabled"),
        Output("slider-bp",       "disabled"),
        Output("btn-apply-valves","disabled"),
        Output("btn-reset",       "disabled"),
        Input("store-simulation-data", "data"),
    )
    def lock_valve_controls_on_trip(d):
        d = d or {}
        tripped = bool(d.get("tripped")) \
                  or (d.get("status") or "").upper() == "TRIPPED" \
                  or (d.get("machine_state") or "").upper() == "TRIPPED"
        return (tripped,) * 6

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
        State("slider-bp", "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_valves(_, v1, v2, v3, vbp, operator):
        operator = operator or "Opérateur"
        try:
            r = _session.post(
                f"{BACKEND}/simulation/valves?operator={operator}",
                json={"valve_v1": v1, "valve_v2": v2, "valve_v3": v3, "valve_bp": vbp},
                timeout=2,
            )
            data = r.json() if r.status_code == 200 else {}
            rejections = data.get("rejections", {})
            ts = datetime.now().strftime("%H:%M:%S")
            msg = f"[{ts}] Vannes → V1:{v1}%  V2:{v2}%  V3:{v3}%  BP:{vbp}%"
            if rejections:
                msg += f" | ⚠ Refusé: {'; '.join(f'{k}={m}' for k,m in rejections.items())}"
            return msg
        except Exception as e:
            return f"Erreur : {e}"

    # ── Reset nominal ─────────────────────────────────────────────────
    @app.callback(
        Output("valve-feedback", "children", allow_duplicate=True),
        Output("slider-v1", "value"),
        Output("slider-v2", "value"),
        Output("slider-v3", "value"),
        Output("slider-bp", "value"),
        Input("btn-reset", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def reset_system(_, operator):
        operator = operator or "Opérateur"
        try:
            _session.post(f"{BACKEND}/simulation/reset?operator={operator}",
                          json={"confirm": True}, timeout=2)
            ts = datetime.now().strftime("%H:%M:%S")
            return f"[{ts}] Système réinitialisé à l'état nominal", 100, 100, 100, 80
        except Exception as e:
            return f"Erreur reset : {e}", no_update, no_update, no_update, no_update

    # ── Déclenchement scénario (Pattern Matching) ─────────────────────
    @app.callback(
        Output("scenario-feedback", "children", allow_duplicate=True),
        Input({"type": "btn-scenario", "index": dash.ALL}, "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def trigger_dynamic_scenario(n_clicks_list, operator):
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

        operator = operator or "Opérateur"
        try:
            r = _session.post(
                f"{BACKEND}/simulation/scenario?operator={operator}",
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
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def stop_scenario(_, operator):
        operator = operator or "Opérateur"
        try:
            _session.post(f"{BACKEND}/simulation/stop?operator={operator}", timeout=2)
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
        tripped = bool(d.get("tripped")) \
                  or (d.get("status") or "").upper() == "TRIPPED" \
                  or (d.get("machine_state") or "").upper() == "TRIPPED"
        active_name = d.get("scenario")

        children, classes, disabled_list = [], [], []
        for name in btn_names:
            if tripped:
                children.append("⛔ AU ACTIF")
                classes.append("btn btn-scenario disabled-scenario-btn")
                disabled_list.append(True)
            elif not active_name:
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

    # ── Panneau Scénario : nom + statut uniquement (la table SCADA gère le reste) ──
    @app.callback(
        Output("sim-scenario-panel", "children"),
        Output("btn-stop-scenario",  "style"),
        Input("store-simulation-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_sim_scenario(d, pathname):
        if pathname != "/simulation":
            return no_update, no_update
        d = d or {}

        from callbacks.cb_control import _fuse_state_badge
        status, s_color = _fuse_state_badge(d)
        _scen       = d.get("scenario") or "Aucun (Nominal)"
        _scen_short = (_scen[:26] + "…") if len(_scen) > 28 else _scen
        has_scenario = d.get("scenario") is not None

        row_style = {
            "fontFamily": "Share Tech Mono", "fontSize": "11px",
            "minHeight": "22px", "display": "flex",
            "alignItems": "center", "marginBottom": "6px",
        }

        panel = html.Div([
            html.Div([
                html.Span("Actif: ", style={"color": "#475569", "flexShrink": "0"}),
                html.Span(
                    _scen_short,
                    title=_scen,
                    style={
                        "color": "#818cf8" if has_scenario else "#64748b",
                        "fontWeight": "700",
                        "whiteSpace": "nowrap",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                ),
            ], style=row_style),
            html.Div([
                html.Span("Statut: ", style={"color": "#475569", "flexShrink": "0"}),
                html.Span(status, style={"color": s_color, "fontWeight": "700"}),
            ], style=row_style),
        ])

        stop_style = ({
            "marginTop": "10px",
            "width": "100%",
            "display": "block",
            "fontSize": "11px",
            "padding": "6px 12px",
            "opacity": "0.85",
        } if has_scenario else {"display": "none"})

        return panel, stop_style

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

