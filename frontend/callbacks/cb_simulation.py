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
    # ── Accordéon horizontal : 1 seul callback pour les 4 sections ──────────
    @app.callback(
        Output("collapse-valves",      "style"),
        Output("collapse-sandbox-ctrl","style"),
        Output("collapse-scenarios",   "style"),
        Output("collapse-history",     "style"),
        Output("toggle-valves",        "children"),
        Output("toggle-sandbox-ctrl",  "children"),
        Output("toggle-scenarios",     "children"),
        Output("toggle-history",       "children"),
        Output("section-valves-wrap",       "style"),
        Output("section-sandbox-ctrl-wrap", "style"),
        Output("section-scenarios-wrap",    "style"),
        Output("section-history-wrap",      "style"),
        Input("toggle-valves-btn",       "n_clicks"),
        Input("toggle-sandbox-ctrl-btn", "n_clicks"),
        Input("toggle-scenarios-btn",    "n_clicks"),
        Input("toggle-history-btn",      "n_clicks"),
        State("collapse-valves",       "style"),
        State("collapse-sandbox-ctrl", "style"),
        State("collapse-scenarios",    "style"),
        State("collapse-history",      "style"),
        prevent_initial_call=True,
    )
    def accordion_toggle(n_v, n_sc, n_s, n_h, s_v, s_sc, s_s, s_h):
        triggered = dash.callback_context.triggered_id

        was_open = {
            "toggle-valves-btn":       (s_v  or {}).get("display") != "none",
            "toggle-sandbox-ctrl-btn": (s_sc or {}).get("display") != "none",
            "toggle-scenarios-btn":    (s_s  or {}).get("display") != "none",
            "toggle-history-btn":      (s_h  or {}).get("display") != "none",
        }
        keys = ["toggle-valves-btn", "toggle-sandbox-ctrl-btn", "toggle-scenarios-btn", "toggle-history-btn"]

        if triggered not in keys:
            return (no_update,) * 12

        if was_open[triggered]:
            new_open = {k: False for k in keys}
        else:
            new_open = {k: (k == triggered) for k in keys}

        def body(k):  return _SHOW if new_open[k] else _HIDE
        def wrap(k):  return _WRAP_EXPANDED if new_open[k] else _WRAP_COLLAPSED
        def arrow(k): return "▼" if new_open[k] else "▶"

        v, sc, s, h = keys
        return (
            body(v), body(sc), body(s), body(h),
            arrow(v), arrow(sc), arrow(s), arrow(h),
            wrap(v), wrap(sc), wrap(s), wrap(h),
        )
    
    # ── Toast bac à sable / scénario (page Simulation uniquement) ─────
    app.clientside_callback(
        """
        function(data) {
            if (!data) return window.dash_clientside.no_update;
            var container = document.getElementById('global-toast-container');
            if (!container) return window.dash_clientside.no_update;

            var cls = 'app-toast app-toast-' + (data.type || 'info');
            var icon = data.type === 'success' ? '\\u2705' : '\\uD83E\\uDDEA';

            var toast = document.createElement('div');
            toast.className = cls;
            toast.innerHTML =
                '<span class="app-toast-icon">' + icon + '</span>' +
                '<div class="app-toast-body">' +
                  '<div class="app-toast-title">' + (data.title || '') + '</div>' +
                  '<div class="app-toast-message">' + (data.message || '') + '</div>' +
                '</div>' +
                '<span class="app-toast-close">\\u2715</span>';

            toast.querySelector('.app-toast-close').onclick = function() {
                toast.remove();
            };

            container.appendChild(toast);
            setTimeout(function() { toast.remove(); }, 6000);

            return '';
        }
        """,
        Output("sim-toast-dummy", "children"),
        Input("sim-toast-store", "data"),
        prevent_initial_call=True,
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

    # ── Verrouillage des contrôles vannes : AU ou bac à sable désactivé ──
    @app.callback(
        Output("slider-v1",       "disabled"),
        Output("slider-v2",       "disabled"),
        Output("slider-v3",       "disabled"),
        Output("slider-bp",       "disabled"),
        Output("btn-apply-valves","disabled"),
        Output("btn-reset",       "disabled"),
        Input("store-simulation-data", "data"),
    )
    def lock_valve_controls(d):
        d = d or {}
        tripped = bool(d.get("tripped")) \
                  or (d.get("status") or "").upper() == "TRIPPED" \
                  or (d.get("machine_state") or "").upper() == "TRIPPED"
        locked = tripped or not bool(d.get("sandbox_active"))
        return (locked,) * 6

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
        Output("sim-toast-store", "data", allow_duplicate=True),
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
            msg = f"V1:{v1}%  V2:{v2}%  V3:{v3}%  BP:{vbp}%"
            if rejections:
                msg += f" | ⚠ Refusé: {'; '.join(f'{k}={m}' for k,m in rejections.items())}"
            return {
                "title": "Vannes", "message": msg,
                "type": "info" if not rejections else "error",
                "n": datetime.now().timestamp(),
            }
        except Exception as e:
            return {"title": "Vannes", "message": f"Erreur : {e}", "type": "error", "n": datetime.now().timestamp()}

    # ── Reset nominal ─────────────────────────────────────────────────
    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
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
            toast = {"title": "Réinitialisation", "message": "Vannes réinitialisées à l'état nominal",
                     "type": "success", "n": datetime.now().timestamp()}
            return toast, 100, 100, 100, 80
        except Exception as e:
            toast = {"title": "Réinitialisation", "message": f"Erreur reset : {e}",
                     "type": "error", "n": datetime.now().timestamp()}
            return toast, no_update, no_update, no_update, no_update

    # ── Déclenchement scénario (Pattern Matching) ─────────────────────
    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
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
            return {
                "title": "Scénario déclenché",
                "message": f"N°{scenario_id} — {name}",
                "type": "info",
                "n": datetime.now().timestamp(),
            }
        except Exception as e:
            return {"title": "Scénario", "message": f"Erreur scénario : {e}",
                    "type": "error", "n": datetime.now().timestamp()}

    # ── Arrêter le scénario ───────────────────────────────────────────
    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
        Input("btn-stop-scenario", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def stop_scenario(_, operator):
        operator = operator or "Opérateur"
        try:
            _session.post(f"{BACKEND}/simulation/stop?operator={operator}", timeout=2)
            return {"title": "Scénario", "message": "Scénario arrêté manuellement",
                    "type": "info", "n": datetime.now().timestamp()}
        except Exception as e:
            return {"title": "Scénario", "message": f"Erreur arrêt : {e}",
                    "type": "error", "n": datetime.now().timestamp()}

    # ── Reset machine simulée (efface un trip simulé) ─────────────────
    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
        Input("btn-reset-sim", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def reset_sim_machine_cb(n, operator):
        if not n:
            return no_update
        operator = operator or "Opérateur"
        try:
            _session.post(f"{BACKEND}/simulation/reset-sim?operator={operator}", timeout=2)
            return {"title": "Machine simulée", "message": "Réinitialisée (re-sync sur la machine réelle)",
                    "type": "success", "n": datetime.now().timestamp()}
        except Exception as e:
            return {"title": "Machine simulée", "message": f"Erreur reset sim : {e}",
                    "type": "error", "n": datetime.now().timestamp()}

    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
        Output("dd-avr-mode", "value"),
        Output("slider-avr-voltage", "value"),
        Output("slider-avr-cosphi", "value"),
        Output("slider-avr-efd", "value"),
        Output("slider-lube-press-offset", "value"),
        Output("slider-lube-temp-offset", "value"),
        Input("btn-reset-controls", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def reset_sim_controls_cb(n, operator):
        if not n:
            return (no_update,) * 7
        operator = operator or "Opérateur"
        try:
            _session.post(f"{BACKEND}/simulation/reset-controls?operator={operator}", timeout=2)
            toast = {"title": "ESV/AVR/Lubrification", "message": "Réinitialisés à l'état nominal",
                     "type": "success", "n": datetime.now().timestamp()}
            return toast, "VOLTAGE", 10.5, 0.85, 1.0, 0.0, 0
        except Exception as e:
            toast = {"title": "ESV/AVR/Lubrification", "message": f"Erreur reset contrôles : {e}",
                     "type": "error", "n": datetime.now().timestamp()}
            return (toast,) + (no_update,) * 6

    # ── ESV sandbox (scénario actif requis, comme AVR/lubrification) ──.
    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
        Input("btn-esv-open", "n_clicks"),
        Input("btn-esv-close", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_esv(n_open, n_close, operator):
        triggered = ctx.triggered_id
        if triggered not in ("btn-esv-open", "btn-esv-close"):
            return no_update
        open_ = (triggered == "btn-esv-open")
        operator = operator or "Opérateur"
        try:
            _session.post(
                f"{BACKEND}/simulation/esv?operator={operator}",
                json={"open": open_, "operator": operator},
                timeout=2,
            )
            return {"title": "ESV (simulation)", "message": f"ESV → {'ouverte' if open_ else 'fermée'}",
                    "type": "info", "n": datetime.now().timestamp()}
        except Exception as e:
            return {"title": "ESV (simulation)", "message": f"Erreur ESV : {e}",
                    "type": "error", "n": datetime.now().timestamp()}
        
    # ── AVR sandbox (scénario actif requis) ────────────────────────────
    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
        Input("btn-apply-avr", "n_clicks"),
        State("dd-avr-mode", "value"),
        State("slider-avr-voltage", "value"),
        State("slider-avr-cosphi", "value"),
        State("slider-avr-efd", "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_avr(_, mode, voltage, cosphi, efd, operator):
        operator = operator or "Opérateur"
        try:
            r_mode = _session.post(
                f"{BACKEND}/simulation/avr/mode",
                json={"mode": mode, "operator": operator},
                timeout=2,
            )
            data_mode = r_mode.json()
            if not data_mode.get("accepted", True):
                return {"title": "AVR (simulation)", "message": data_mode.get("message"),
                        "type": "error", "n": datetime.now().timestamp()}

            _session.post(
                f"{BACKEND}/simulation/avr/setpoint",
                json={"voltage_kv": voltage, "cosphi": cosphi, "operator": operator},
                timeout=2,
            )
            if mode == "MANUAL":
                _session.post(
                    f"{BACKEND}/simulation/avr/efd",
                    json={"e_fd_pu": efd, "operator": operator},
                    timeout=2,
                )
            extra = f", E_fd={efd}p.u." if mode == "MANUAL" else ""
            return {"title": "AVR (simulation)",
                    "message": f"Mode {mode}, V_set={voltage}kV, cosφ_set={cosphi}{extra}",
                    "type": "info", "n": datetime.now().timestamp()}
        except Exception as e:
            return {"title": "AVR (simulation)", "message": f"Erreur AVR : {e}",
                    "type": "error", "n": datetime.now().timestamp()}

    # ── Lubrification sandbox (scénario actif requis) ──────────────────
    @app.callback(
        Output("sim-toast-store", "data", allow_duplicate=True),
        Input("btn-apply-lube", "n_clicks"),
        State("slider-lube-press-offset", "value"),
        State("slider-lube-temp-offset", "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_lube(_, p_off, t_off, operator):
        operator = operator or "Opérateur"
        try:
            r = _session.post(
                f"{BACKEND}/simulation/lubrication",
                json={"press_offset": p_off, "temp_offset": t_off, "operator": operator},
                timeout=2,
            )
            data = r.json()
            if not data.get("accepted", True):
                return {"title": "Lubrification (simulation)", "message": data.get("message"),
                        "type": "error", "n": datetime.now().timestamp()}
            return {"title": "Lubrification (simulation)",
                    "message": f"ΔP={p_off} bar, ΔT={t_off} °C",
                    "type": "info", "n": datetime.now().timestamp()}
        except Exception as e:
            return {"title": "Lubrification (simulation)", "message": f"Erreur lubrification : {e}",
                    "type": "error", "n": datetime.now().timestamp()}
        
    # ── Verrouillage AVR/lubrification/ESV hors fork (scénario ou bac à sable) ──
    @app.callback(
        Output("dd-avr-mode",              "disabled"),
        Output("slider-avr-voltage",       "disabled"),
        Output("slider-avr-cosphi",        "disabled"),
        Output("slider-avr-efd",           "disabled"),
        Output("btn-apply-avr",            "disabled"),
        Output("slider-lube-press-offset", "disabled"),
        Output("slider-lube-temp-offset",  "disabled"),
        Output("btn-apply-lube",           "disabled"),
        Output("btn-esv-open",             "disabled"),
        Output("btn-esv-close",            "disabled"),
        Input("store-simulation-data", "data"),
    )
    def lock_sandbox_controls(d):
        d = d or {}
        no_fork = not bool(d.get("sandbox_active"))
        return (no_fork,) * 10

    # ── Bascule bac à sable manuel ──────────────────────────────────────
    @app.callback(
        Output("sim-toast-store", "data"),
        Input("btn-sandbox-toggle", "n_clicks"),
        State("store-simulation-data", "data"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_sandbox_toggle(_, d, operator):
        operator = operator or "Opérateur"
        d = d or {}
        new_active = not bool(d.get("sandbox_active"))
        try:
            _session.post(
                f"{BACKEND}/simulation/sandbox",
                json={"active": new_active, "operator": operator},
                timeout=2,
            )
            return {
                "title": "Bac à sable",
                "message": "Activé — vannes, ESV, AVR et scénarios accessibles."
                            if new_active else
                            "Désactivé — retour aux données réelles (mode lecture).",
                "type": "success" if new_active else "info",
                "n": datetime.now().timestamp(),
            }
        except Exception as e:
            return {"title": "Bac à sable", "message": f"Erreur bac à sable : {e}",
                    "type": "error", "n": datetime.now().timestamp()}

    # ── Synchronisation du bandeau Mode sur l'état réel (sandbox_active) ──
    @app.callback(
        Output("sandbox-mode-label", "children"),
        Output("sandbox-mode-label", "style"),
        Output("sandbox-mode-hint", "children"),
        Output("btn-sandbox-toggle", "children"),
        Input("store-simulation-data", "data"),
    )
    def sync_sandbox_banner(d):
        d = d or {}
        active = bool(d.get("sandbox_active"))
        if active:
            return (
                "Bac à sable ACTIF",
                {"fontWeight": "700", "fontSize": "12px", "color": "#22c55e", "marginRight": "12px"},
                "Vannes, ESV, AVR, lubrification et scénarios pilotables sur la copie "
                "isolée de la machine, sans impact sur le flux réel.",
                "🧪 Désactiver bac à sable",
            )
        return (
            "Lecture (données réelles)",
            {"fontWeight": "700", "fontSize": "12px", "color": "#64748b", "marginRight": "12px"},
            "Activez le bac à sable pour piloter les vannes et tester des scénarios "
            "sans perturber la machine réelle.",
            "🧪 Activer bac à sable",
        )

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
        sandbox_active = bool(d.get("sandbox_active"))
        machine_state = (d.get("machine_state") or "").upper()
        tripped = bool(d.get("tripped")) \
                  or (d.get("status") or "").upper() == "TRIPPED" \
                  or machine_state == "TRIPPED"
        is_stopped  = machine_state == "STOPPED"
        not_running = machine_state not in ("GRID_CONNECTED",)
        active_name = d.get("scenario")

        children, classes, disabled_list = [], [], []
        for name in btn_names:
            if not sandbox_active:
                children.append("🔒 Bac à sable requis")
                classes.append("btn btn-scenario disabled-scenario-btn")
                disabled_list.append(True)
            elif tripped:
                children.append("⛔ AU ACTIF")
                classes.append("btn btn-scenario disabled-scenario-btn")
                disabled_list.append(True)
            elif is_stopped:
                children.append("⛔ MACHINE À L'ARRÊT")
                classes.append("btn btn-scenario disabled-scenario-btn")
                disabled_list.append(True)
            elif not_running:
                children.append("⛔ MACHINE EN DÉMARRAGE")
                classes.append("btn btn-scenario disabled-scenario-btn")
                disabled_list.append(True)
            elif name == active_name:
                children.append("🛑 EN COURS...")
                classes.append("btn btn-scenario active-scenario-btn")
                disabled_list.append(True)
            elif active_name:
                children.append("▶ DÉCLENCHER")
                classes.append("btn btn-scenario disabled-scenario-btn")
                disabled_list.append(True)
            else:
                children.append("▶ DÉCLENCHER")
                classes.append("btn btn-scenario")
                disabled_list.append(False)
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
        tripped = bool(d.get("tripped")) \
                  or (d.get("status") or "").upper() == "TRIPPED" \
                  or (d.get("machine_state") or "").upper() == "TRIPPED"

        # Machine simulée (bac à sable) découplée/arrêtée — ex: ESV fermée → ROLLING/STOPPED
        # sans passer par TRIPPED : propose aussi le reset dans ce cas.
        sandbox_active = bool(d.get("sandbox_active"))
        sim_state      = (d.get("machine_state") or "").upper()
        sim_stopped    = sandbox_active and sim_state in ("ROLLING", "STOPPED")
        show_reset_sim = tripped or sim_stopped

        row_style = {
            "fontFamily": "Share Tech Mono", "fontSize": "11px",
            "minHeight": "22px", "display": "flex",
            "alignItems": "center", "marginBottom": "6px",
        }

        children = [
            html.Div([
                html.Span("Actif: ", style={"color": "#475569", "flexShrink": "0"}),
                html.Span(
                    _scen_short, title=_scen,
                    style={
                        "color": "#818cf8" if has_scenario else "#64748b",
                        "fontWeight": "700", "whiteSpace": "nowrap",
                        "overflow": "hidden", "textOverflow": "ellipsis",
                    },
                ),
            ], style=row_style),
            html.Div([
                html.Span("Statut: ", style={"color": "#475569", "flexShrink": "0"}),
                html.Span(status, style={"color": s_color, "fontWeight": "700"}),
            ], style=row_style),
        ]

        if show_reset_sim:
            children.append(html.Button(
                "↻ RESET MACHINE SIMULÉE",
                id="btn-reset-sim", n_clicks=0,
                className="btn",
                style={
                    "marginTop": "8px", "width": "100%", "display": "block",
                    "fontSize": "11px", "padding": "6px 12px",
                    "background": "#7f1d1d", "color": "#fecaca",
                    "border": "1px solid #ef4444", "borderRadius": "4px",
                    "cursor": "pointer", "fontFamily": "Share Tech Mono",
                },
            ))

        panel = html.Div(children)

        stop_style = ({
            "marginTop": "10px", "width": "100%", "display": "block",
            "fontSize": "11px", "padding": "6px 12px", "opacity": "0.85",
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
                history = list(reversed(r.json()))
                if not history:
                    return html.Div("Aucun scénario déclenché",
                                     style={"color": "#64748b", "fontSize": "11px",
                                            "fontFamily": "Share Tech Mono", "padding": "10px"})
                items = []
                for item in history:
                    sid = item.get("id", 0)
                    _, color = _CRITICITE.get(sid, ("MODÉRÉ", "#818cf8"))
                    items.append(html.Div([
                        html.Span(f"#{sid}", style={
                            "color": color, "fontFamily": "Share Tech Mono",
                            "fontSize": "10px", "border": f"1px solid {color}66",
                            "borderRadius": "3px", "padding": "1px 5px", "flexShrink": "0",
                        }),
                        html.Span(item.get("name", "?"), className="history-name",
                                  style={"flex": "1"}),
                        html.Span(item.get("timestamp", ""), className="history-ts"),
                    ], className="history-item", style={"borderLeftColor": color}))
                return items
        except Exception:
            pass
        return html.Div("Erreur historique", style={
            "color": "#ef4444", "fontFamily": "Share Tech Mono",
            "fontSize": "11px", "padding": "10px",
        })