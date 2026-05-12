"""
callbacks/cb_control.py — Callbacks page Contrôle Commande GTA
"""
import requests
from dash import Input, Output, State, html, no_update, ctx
from config import BACKEND
from components.alert_banner import alert_item, alerts_panel

_session = requests.Session()


def _status_ok(text):
    return html.Span(text, style={"color": "#22c55e", "fontFamily": "Share Tech Mono", "fontSize": "11px"})


def _status_err(text):
    return html.Span(text, style={"color": "#ef4444", "fontFamily": "Share Tech Mono", "fontSize": "11px"})


def _post(path, json_body=None, params=None):
    try:
        r = _session.post(f"{BACKEND}{path}", json=json_body, params=params, timeout=5)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def _get(path, params=None):
    try:
        r = _session.get(f"{BACKEND}{path}", params=params, timeout=5)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def register(app):

    # ── Mise à jour temps réel : état système depuis WebSocket nominal ──
    @app.callback(
        Output("ctrl-status-badge", "children"),
        Output("ctrl-status-badge", "style"),
        Input("store-current-data", "data"),
        prevent_initial_call=False,
    )
    def update_status_badge(data):
        if not data:
            return "—", {"fontSize": "16px", "fontWeight": "700",
                          "fontFamily": "Share Tech Mono", "color": "#64748b"}
        status = data.get("status", "NORMAL")
        status_color = {"NORMAL": "#00e676", "DEGRADED": "#f59e0b",
                        "CRITICAL": "#ef4444"}.get(status, "#64748b")
        return status, {"fontSize": "16px", "fontWeight": "700",
                        "fontFamily": "Share Tech Mono", "color": status_color}

    # ── Polling 1s : badge + PID + séquence + interlocks ────────────
    # Le radio (ctrl-mode-radio) n'est JAMAIS écrit par callback :
    # il est toujours sous contrôle de l'utilisateur.
    # Le badge (ctrl-mode-badge) reflète l'état réel du backend.
    @app.callback(
        Output("ctrl-mode-badge",        "children"),
        Output("ctrl-mode-badge",        "style"),
        Output("ctrl-tripped-banner",    "style"),
        Output("ctrl-btn-reset-trip",    "style"),
        Output("ctrl-pid-error-val",     "children"),
        Output("ctrl-pid-output-val",    "children"),
        Output("ctrl-seq-progress-wrap", "style"),
        Output("ctrl-seq-bar",           "style"),
        Output("ctrl-seq-label",         "children"),
        Output("ctrl-interlocks-list",   "children"),
        # AVR
        Output("ctrl-avr-vt-val",        "children"),
        Output("ctrl-avr-efd-val",       "children"),
        Output("ctrl-avr-cosphi-val",    "children"),
        Output("ctrl-avr-sat-badge",     "children"),
        Output("ctrl-avr-sat-badge",     "style"),
        Input("ctrl-state-interval",     "n_intervals"),
        Input("url",                     "pathname"),
        prevent_initial_call=False,
    )
    def poll_control_state(n, pathname):
        if pathname != "/control":
            return (no_update,) * 15

        state, err = _get("/control/state")
        if err or not state:
            return (no_update,) * 15

        mode    = state.get("control_mode", "MANUAL")
        tripped = state.get("tripped", False)

        # Badge mode
        mode_color = {"MANUAL": "#f97316", "AUTO": "#22c55e"}.get(mode, "#60a5fa")
        mode_style = {"fontSize": "18px", "fontWeight": "700",
                      "fontFamily": "Share Tech Mono", "letterSpacing": "2px",
                      "color": mode_color}

        # Trip banner + bouton reset
        tripped_style   = {"display": "block"} if tripped else {"display": "none"}
        reset_btn_style = {
            "display": "block" if tripped else "none",
            "fontSize": "11px", "padding": "6px 14px",
            "background": "#22c55e", "border": "1px solid #22c55e", "marginTop": "8px",
        }

        # PID
        pid_err = state.get("pid_error")
        pid_out = state.get("pid_output")
        pid_err_str = f"{pid_err:+.3f}" if pid_err is not None else "—"
        pid_out_str = f"{pid_out:.1f}"   if pid_out is not None else "—"

        # Séquence
        seq_state    = state.get("sequence_state", "IDLE")
        seq_progress = state.get("sequence_progress")
        if seq_state in ("STARTING", "STOPPING") and seq_progress is not None:
            prog_pct  = round(seq_progress * 100)
            seq_wrap  = {"display": "block"}
            bar_style = {"height": "8px", "background": "#8b5cf6",
                         "borderRadius": "4px", "width": f"{prog_pct}%",
                         "transition": "width 0.5s ease"}
            seq_lbl   = f"{seq_state} — {prog_pct}%"
        else:
            seq_wrap  = {"display": "none"}
            bar_style = {"height": "8px", "background": "#8b5cf6",
                         "borderRadius": "4px", "width": "0%"}
            seq_lbl   = ""

        # Interlocks
        warnings = state.get("interlock_warnings", [])
        interlock_children = []
        if warnings:
            for w in warnings:
                interlock_children.append(html.Div([
                    html.Span("⚠ ", style={"color": "#f59e0b"}),
                    html.Span(w, style={"fontSize": "11px", "fontFamily": "Share Tech Mono",
                                        "color": "#f59e0b"}),
                ], style={"marginBottom": "4px"}))
        else:
            interlock_children.append(html.Div([
                html.Span("✅ ", style={"color": "#22c55e"}),
                html.Span("Tous les interlocks OK", style={
                    "fontSize": "11px", "fontFamily": "Share Tech Mono", "color": "#22c55e",
                }),
            ]))

        # Interlock BP/V1 depuis l'état des vannes
        vs   = state.get("valve_state", {})
        v1   = (vs.get("v1") or {}).get("current", 0)
        bp   = (vs.get("bp") or {}).get("current", 0)
        bp_ok = not (v1 > 10 and bp < 5)
        interlock_children.append(html.Div([
            html.Span("✅ " if bp_ok else "❌ ", style={"color": "#22c55e" if bp_ok else "#ef4444"}),
            html.Span("BP ≥ 5% si V1 > 10%", style={
                "fontSize": "11px", "fontFamily": "Share Tech Mono",
                "color": "#22c55e" if bp_ok else "#ef4444",
            }),
        ], style={"marginTop": "4px"}))

        # AVR
        avr_vt     = state.get("avr_v_term")
        avr_efd    = state.get("avr_e_fd_pu")
        avr_cphi   = state.get("avr_cosphi")
        avr_sat    = state.get("avr_saturated", False)
        avr_vt_str   = f"{avr_vt:.3f}"  if avr_vt  is not None else "—"
        avr_efd_str  = f"{avr_efd:.4f}" if avr_efd  is not None else "—"
        avr_cphi_str = f"{avr_cphi:.3f}" if avr_cphi is not None else "—"
        if avr_sat and avr_efd is not None:
            sat_label = "SAT MAX" if avr_efd >= 2.4 else "SAT MIN"
            sat_style = {
                "fontSize": "9px", "fontFamily": "Share Tech Mono", "fontWeight": "700",
                "letterSpacing": "0.5px", "padding": "2px 6px", "borderRadius": "4px",
                "color": "#ef4444", "background": "rgba(239,68,68,0.15)",
                "border": "1px solid #ef4444",
            }
        else:
            sat_label = ""
            sat_style = {"fontSize": "9px", "padding": "2px 6px"}

        return (
            mode, mode_style,
            tripped_style, reset_btn_style,
            pid_err_str, pid_out_str,
            seq_wrap, bar_style, seq_lbl,
            interlock_children,
            avr_vt_str, avr_efd_str, avr_cphi_str, sat_label, sat_style,
        )

    # ── Dialogue confirmation AU ─────────────────────────────────────
    @app.callback(
        Output("ctrl-confirm-au", "displayed"),
        Input("ctrl-btn-au", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_au_dialog(n):
        return True

    # ── Exécution AU — div dédié ─────────────────────────────────────
    @app.callback(
        Output("ctrl-au-status", "children"),
        Input("ctrl-confirm-au", "submit_n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def execute_au(n, operator):
        if not n:
            return no_update
        data, err = _post("/control/emergency/trip",
                          {"confirm": True, "operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur AU : {err}")
        return _status_err("⚠ TRIP EXÉCUTÉ")

    # ── Reset Trip — div dédié ───────────────────────────────────────
    @app.callback(
        Output("ctrl-trip-status", "children"),
        Input("ctrl-btn-reset-trip", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def reset_trip(n, operator):
        if not n:
            return no_update
        data, err = _post("/control/emergency/reset", params={"operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok("✓ Trip réinitialisé.")

    # ── Changer mode — div dédié ─────────────────────────────────────
    @app.callback(
        Output("ctrl-mode-apply-status", "children"),
        Input("ctrl-btn-mode", "n_clicks"),
        State("ctrl-mode-radio",     "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_mode(n, mode, operator):
        if not n:
            return no_update
        data, err = _post("/control/mode", {"mode": mode, "operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok(f"✓ Mode {mode} appliqué")

    # ── Appliquer consignes ──────────────────────────────────────────
    @app.callback(
        Output("ctrl-setpoints-status", "children"),
        Input("ctrl-btn-setpoints", "n_clicks"),
        State("ctrl-sp-power",    "value"),
        State("ctrl-sp-speed",    "value"),
        State("ctrl-sp-pressure", "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_setpoints(n, power, speed, pressure, operator):
        if not n:
            return no_update
        sp = {}
        if power    is not None: sp["power_mw"]        = power
        if speed    is not None: sp["speed_rpm"]        = speed
        if pressure is not None: sp["pressure_hp_bar"]  = pressure
        if not sp:
            return _status_err("Aucune consigne saisie.")
        data, err = _post("/control/setpoints",
                          {"setpoints": sp, "operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur : {err}")
        parts = []
        if power    is not None: parts.append(f"P={power} MW")
        if speed    is not None: parts.append(f"N={speed} RPM")
        if pressure is not None: parts.append(f"P_HP={pressure} bar")
        return _status_ok(f"✓ Consignes : {' | '.join(parts)}")

    # ── Affichage valeurs sliders vannes ─────────────────────────────
    @app.callback(
        Output("val-ctrl-v1", "children"),
        Output("val-ctrl-v2", "children"),
        Output("val-ctrl-v3", "children"),
        Output("val-ctrl-bp", "children"),
        Input("slider-ctrl-v1", "value"),
        Input("slider-ctrl-v2", "value"),
        Input("slider-ctrl-v3", "value"),
        Input("slider-ctrl-bp", "value"),
    )
    def update_valve_displays(v1, v2, v3, vbp):
        return str(v1 or 0), str(v2 or 0), str(v3 or 0), str(vbp or 0)

    # ── Appliquer commande vannes ────────────────────────────────────
    @app.callback(
        Output("ctrl-valves-status", "children"),
        Input("ctrl-btn-valves", "n_clicks"),
        State("slider-ctrl-v1", "value"),
        State("slider-ctrl-v2", "value"),
        State("slider-ctrl-v3", "value"),
        State("slider-ctrl-bp", "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_valves(n, v1, v2, v3, vbp, operator):
        if not n:
            return no_update
        body = {"operator": operator or "Opérateur"}
        if v1  is not None: body["valve_v1"] = v1
        if v2  is not None: body["valve_v2"] = v2
        if v3  is not None: body["valve_v3"] = v3
        if vbp is not None: body["valve_bp"] = vbp
        data, err = _post("/control/valve", body)
        if err:
            return _status_err(f"Erreur : {err}")
        # Résumé des refus éventuels
        results = data.get("results", {})
        rejets = [f"{k}: {v.get('message')}" for k, v in results.items() if not v.get("accepted")]
        if rejets:
            return _status_err("Refusé — " + " | ".join(rejets))
        return _status_ok(f"✓ Vannes envoyées : V1={v1}% V2={v2}% V3={v3}% BP={vbp}%")

    # ── Séquences ────────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-seq-status", "children"),
        Input("ctrl-btn-seq-start",  "n_clicks"),
        Input("ctrl-btn-seq-stop",   "n_clicks"),
        Input("ctrl-btn-seq-cancel", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def sequence_action(n_start, n_stop, n_cancel, operator):
        op = operator or "Opérateur"
        triggered = ctx.triggered_id
        if triggered == "ctrl-btn-seq-start":
            data, err = _post("/control/sequence/start", {"sequence": "start_turbine", "operator": op})
        elif triggered == "ctrl-btn-seq-stop":
            data, err = _post("/control/sequence/stop", {"sequence": "stop_turbine", "operator": op})
        elif triggered == "ctrl-btn-seq-cancel":
            data, err = _post("/control/sequence/cancel", params={"operator": op})
        else:
            return no_update
        if err:
            return _status_err(f"Erreur : {err}")
        msg = data.get("message", "OK")
        return _status_ok(f"✓ {msg}")

    # ── Réglage PID ──────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-pid-status", "children"),
        Input("ctrl-btn-pid", "n_clicks"),
        State("ctrl-pid-kp",    "value"),
        State("ctrl-pid-ki",    "value"),
        State("ctrl-pid-kd",    "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_pid(n, kp, ki, kd, operator):
        if not n:
            return no_update
        if any(v is None for v in [kp, ki, kd]):
            return _status_err("Renseignez Kp, Ki, Kd.")
        data, err = _post("/control/pid",
                          {"kp": kp, "ki": ki, "kd": kd, "operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok(f"✓ PID : Kp={kp} Ki={ki} Kd={kd}")

    # ── AVR — mode + setpoints ──────────────────────────────────────
    @app.callback(
        Output("ctrl-avr-status", "children"),
        Input("ctrl-btn-avr", "n_clicks"),
        State("ctrl-avr-mode",      "value"),
        State("ctrl-avr-vset",      "value"),
        State("ctrl-avr-cosphi-set","value"),
        State("ctrl-avr-efd-manual","value"),
        State("store-operator-name","data"),
        prevent_initial_call=True,
    )
    def apply_avr(n, mode, vset, cosphi_set, efd_manual, operator):
        if not n:
            return no_update
        op = operator or "Opérateur"
        _, err = _post("/control/avr/mode", {"mode": mode, "operator": op})
        if err:
            return _status_err(f"Mode AVR : {err}")
        if mode == "MANUAL" and efd_manual is not None:
            _post("/control/avr/manual", {"e_fd_pu": efd_manual, "operator": op})
        body = {}
        if vset       is not None: body["voltage_kv"] = vset
        if cosphi_set is not None: body["cosphi"]     = cosphi_set
        if body:
            data, err2 = _post("/control/avr/setpoint", {**body, "operator": op})
            if err2:
                return _status_err(f"Consigne AVR : {err2}")
        label = vset if mode == "VOLTAGE" else (cosphi_set if mode == "COSPHI" else efd_manual)
        return _status_ok(f"✓ AVR {mode} → {label}")

    # ── AVR — gains K_A / T_A ────────────────────────────────────────
    @app.callback(
        Output("ctrl-avr-gains-status", "children"),
        Input("ctrl-btn-avr-gains", "n_clicks"),
        State("ctrl-avr-ka",         "value"),
        State("ctrl-avr-ta",         "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_avr_gains(n, ka, ta, operator):
        if not n:
            return no_update
        if any(v is None for v in [ka, ta]):
            return _status_err("Renseignez K_A et T_A.")
        data, err = _post("/control/avr/gains",
                          {"k_a": ka, "t_a": ta, "operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok(f"✓ Gains AVR : K_A={ka}  T_A={ta} s")

    # ── Acquitter tout ───────────────────────────────────────────────
    @app.callback(
        Output("ctrl-alarms-list", "children"),
        Input("ctrl-btn-ack-all", "n_clicks"),
        Input("ctrl-log-interval", "n_intervals"),
        Input("url", "pathname"),
        State("store-operator-name", "data"),
        prevent_initial_call=False,
    )
    def refresh_alarms(n_ack, n_int, pathname, operator):
        if pathname != "/control":
            return no_update

        # Acquittement de toutes les alarmes
        if ctx.triggered_id == "ctrl-btn-ack-all" and n_ack:
            alarms_data, _ = _get("/settings/alerts")
            if alarms_data:
                for a in alarms_data:
                    if not a.get("acknowledged"):
                        _post(f"/settings/alerts/{a['id']}/acknowledge",
                              params={"operator": operator or "Opérateur"})

        alarms_data, err = _get("/settings/alerts")
        if err or not alarms_data:
            return html.Div("Aucune alarme récupérée.", style={
                "fontSize": "11px", "color": "#64748b", "fontFamily": "Share Tech Mono",
            })
        active = [a for a in alarms_data if not a.get("acknowledged")]
        return alerts_panel(active)

    # ── Journal des commandes ────────────────────────────────────────
    @app.callback(
        Output("ctrl-commands-log", "children"),
        Input("ctrl-log-interval", "n_intervals"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def refresh_commands_log(n, pathname):
        if pathname != "/control":
            return no_update
        data, err = _get("/audit/operator-actions", params={"limit": 10})
        if err or not data:
            return html.Div("Aucune commande récente.", style={
                "fontSize": "11px", "color": "#64748b", "fontFamily": "Share Tech Mono",
            })

        _ACTION_COLOR = {
            "MODE_CHANGE":      "#60a5fa",
            "SETPOINT_CHANGE":  "#22c55e",
            "VALVE_COMMAND":    "#f97316",
            "EMERGENCY_TRIP":   "#ef4444",
            "TRIP_RESET":       "#22c55e",
            "SEQUENCE_START":   "#8b5cf6",
            "SEQUENCE_CANCEL":  "#94a3b8",
            "SEQUENCE_COMPLETED": "#22c55e",
            "PID_TUNE":         "#f59e0b",
            "ALERT_ACK":        "#64748b",
            "AVR_MODE_CHANGE":    "#a855f7",
            "AVR_SETPOINT_CHANGE":"#a855f7",
            "AVR_GAINS_CHANGE":   "#a855f7",
            "AVR_EFD_MANUAL":     "#a855f7",
        }

        rows = []
        for a in data[:10]:
            ts  = (a.get("ts") or "")[:19].replace("T", " ")
            act = a.get("action_type", "")
            tgt = a.get("target", "")
            color = _ACTION_COLOR.get(act, "#94a3b8")
            rows.append(html.Div([
                html.Span(ts, style={"color": "#64748b", "fontSize": "9px",
                                     "fontFamily": "Share Tech Mono", "marginRight": "8px",
                                     "minWidth": "120px"}),
                html.Span(act, style={"color": color, "fontSize": "10px",
                                      "fontFamily": "Share Tech Mono", "marginRight": "6px",
                                      "fontWeight": "600"}),
                html.Span(tgt or "", style={"color": "#94a3b8", "fontSize": "10px",
                                             "fontFamily": "Share Tech Mono"}),
            ], style={"display": "flex", "alignItems": "center",
                      "padding": "3px 0", "borderBottom": "1px solid #0f2744"}))

        return rows if rows else html.Div("Aucune commande.", style={
            "fontSize": "11px", "color": "#64748b", "fontFamily": "Share Tech Mono",
        })
