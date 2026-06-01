"""
callbacks/cb_control.py — Callbacks page Contrôle Commande GTA (Cockpit 3 zones)
"""
import requests
from dash import Input, Output, State, html, no_update, ctx, clientside_callback, ALL, MATCH
from config import BACKEND
from components.alert_banner import alert_item, alerts_panel

_session = requests.Session()

_GREYED = {"opacity": "0.4", "pointerEvents": "none", "filter": "grayscale(0.5)"}
_ACTIVE = {}

_STATE_ORDER = ["STOPPED", "ROLLING", "SYNCHRONIZING", "GRID_CONNECTED"]

_PROT_LABELS_FR = {
    # Tier 1 — TRIP
    "OVERSPEED_1":     "Survitesse 110%",
    "OVERSPEED_2":     "Survitesse 115%",
    "LUBE_OIL_LOW":    "Pression huile basse",
    "OIL_PUMP_OFF":    "Pompe huile arrêtée",
    "VIB_TRIP":        "Vibrations excessives",
    "AXIAL_DISP":      "Déplacement axial rotor",
    "BEARING_TEMP":    "Température palier critique",
    "HP_OVERPRESSURE": "Surpression HP",
    "HP_OVERTEMP":     "Surchauffe HP",
    "OVERVOLTAGE":     "Surtension alternateur",
    "OVERCURRENT":     "Surintensité ligne",
    "REVERSE_POWER":   "Puissance inverse",
    # Tier 2 — DISCONNECT
    "LOSS_OF_SYNC":    "Perte de synchronisme",
    "FREQ_DEVIATION":  "Écart fréquence réseau",
    "LOSS_OF_EXCIT":   "Perte d'excitation",
    # Tier 3 — ALARM
    "VIB_ALARM":       "Alarme vibrations",
    "BEARING_ALARM":   "Alarme température palier",
    "OIL_LEVEL_LOW":   "Niveau huile bas",
    "OIL_FILTER_DP":   "ΔP filtre huile élevé",
    "UNDERVOLTAGE":    "Sous-tension alternateur",
}


def _status_ok(text):
    return html.Span(text, style={"color": "#22c55e", "fontFamily": "Share Tech Mono",
                                  "fontSize": "11px"})


def _status_err(text):
    return html.Span(text, style={"color": "#ef4444", "fontFamily": "Share Tech Mono",
                                  "fontSize": "11px"})


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

    # ── Horloge bandeau (clientside — aucun appel réseau) ────────────
    clientside_callback(
        """
        function(n) {
            return new Date().toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
        }
        """,
        Output("ctrl-banner-clock", "children"),
        Input("ctrl-state-interval", "n_intervals"),
    )

    # ── Nom opérateur dans le bandeau ────────────────────────────────
    @app.callback(
        Output("ctrl-banner-operator", "children"),
        Input("store-operator-name", "data"),
    )
    def update_banner_operator(name):
        return name or "—"

    # ── Mise à jour statut système depuis WebSocket ──────────────────
    @app.callback(
        Output("ctrl-status-badge", "children"),
        Output("ctrl-status-badge", "style"),
        Input("store-current-data", "data"),
        prevent_initial_call=False,
    )
    def update_status_badge(data):
        if not data:
            return "—", {"fontSize": "13px", "fontWeight": "700",
                         "fontFamily": "Share Tech Mono", "color": "#64748b"}
        status = data.get("status", "NORMAL")
        color = {"NORMAL": "#00e676", "DEGRADED": "#f59e0b",
                 "CRITICAL": "#ef4444"}.get(status, "#64748b")
        return status, {"fontSize": "13px", "fontWeight": "700",
                        "fontFamily": "Share Tech Mono", "color": color}

    # ── Polling 1s : état complet ────────────────────────────────────
    @app.callback(
        # Bandeau
        Output("ctrl-mode-badge",           "children"),
        Output("ctrl-mode-badge",           "style"),
        Output("ctrl-tripped-banner",       "style"),
        Output("ctrl-btn-reset-trip",       "style"),
        # Machine stepper — className de chaque pastille
        Output("ctrl-step-stopped",         "className"),
        Output("ctrl-step-rolling",         "className"),
        Output("ctrl-step-synchronizing",   "className"),
        Output("ctrl-step-grid_connected",  "className"),
        # Overlays mode/machine-state
        Output("ctrl-setpoints-overlay",    "style"),
        Output("ctrl-valves-overlay",       "style"),
        Output("ctrl-avr-overlay",          "style"),
        Output("ctrl-regul-target-overlay", "style"),
        # Boutons grid
        Output("ctrl-btn-grid-sync",        "disabled"),
        Output("ctrl-btn-grid-disconnect",  "disabled"),
        Output("ctrl-btn-grid-couple",      "disabled"),
        Output("ctrl-sync-criteria",        "children"),
        # PID Power readouts
        Output("ctrl-pid-power-error-val",  "children"),
        Output("ctrl-pid-power-output-val", "children"),
        # PID Speed readouts
        Output("ctrl-pid-speed-error-val",  "children"),
        Output("ctrl-pid-speed-output-val", "children"),
        # Séquence
        Output("ctrl-seq-progress-wrap",    "style"),
        Output("ctrl-seq-bar",              "style"),
        Output("ctrl-seq-label",            "children"),
        # Interlocks
        Output("ctrl-interlocks-list",      "children"),
        # AVR
        Output("ctrl-avr-vt-val",           "children"),
        Output("ctrl-avr-efd-val",          "children"),
        Output("ctrl-avr-cosphi-val",       "children"),
        Output("ctrl-avr-sat-badge",        "children"),
        Output("ctrl-avr-sat-badge",        "style"),
        Output("ctrl-avr-grid-warning",     "style"),
        Input("ctrl-state-interval",        "n_intervals"),
        Input("url",                        "pathname"),
        prevent_initial_call=False,
    )
    def poll_control_state(n, pathname):
        n_out = 30
        if pathname != "/control":
            return (no_update,) * n_out

        state, err = _get("/control/state")
        if err or not state:
            return (no_update,) * n_out

        mode         = state.get("control_mode", "MANUAL")
        machine_state = state.get("machine_state", "STOPPED")
        tripped      = state.get("tripped", False)
        reg_target   = state.get("regulation_target", "POWER")

        # ── Mode badge ──
        mode_color = {"MANUAL": "#f97316", "AUTO": "#22c55e"}.get(mode, "#60a5fa")
        mode_style = {"fontSize": "16px", "fontWeight": "700",
                      "fontFamily": "Share Tech Mono", "letterSpacing": "2px",
                      "color": mode_color}

        # ── Trip ──
        trip_banner_style = {"display": "flex"} if tripped else {"display": "none"}
        reset_btn_style   = {
            "display": "block" if tripped else "none",
            "fontSize": "11px", "padding": "6px 12px",
            "background": "#22c55e", "border": "1px solid #22c55e", "marginRight": "8px",
        }

        # ── Machine stepper (4 classNames) ──
        if tripped:
            step_classes = ["stepper-pill stepper-pill-tripped"] * 4
        else:
            idx = _STATE_ORDER.index(machine_state) if machine_state in _STATE_ORDER else 0
            step_classes = []
            for i in range(4):
                if i < idx:
                    step_classes.append("stepper-pill stepper-pill-done")
                elif i == idx:
                    step_classes.append("stepper-pill stepper-pill-active")
                else:
                    step_classes.append("stepper-pill stepper-pill-future")

        # ── Overlays ──
        setpoints_style  = _GREYED if mode == "MANUAL" else _ACTIVE
        valves_style     = _GREYED if mode == "AUTO"   else _ACTIVE
        avr_style        = _GREYED if machine_state != "GRID_CONNECTED" else _ACTIVE
        reg_target_style = _GREYED if machine_state != "GRID_CONNECTED" else _ACTIVE
        # Avertissement AVR — visible uniquement en GRID_CONNECTED
        avr_warn_style   = {"display": "block"} if machine_state == "GRID_CONNECTED" \
                           else {"display": "none"}

        # ── Grid buttons — pilotés par startup_phase ──
        startup_phase            = state.get("startup_phase", "PRE_CHECKS")
        avr_mode_snap            = state.get("avr_mode", "OFF")
        # Sync arm : disponible en phase EXCITED (avant SYNCHRONIZING)
        grid_sync_disabled       = startup_phase != "EXCITED" or tripped
        grid_disconnect_disabled = machine_state != "GRID_CONNECTED"
        # Couplage : disponible uniquement en phase SYNCHRONIZING avec excitation + fréquence OK
        freq_snap  = state.get("grid_frequency", 0.0) or 0.0
        freq_ok    = 49.9 <= freq_snap <= 50.1
        excit_ok   = avr_mode_snap != "OFF"
        couple_disabled = startup_phase != "SYNCHRONIZING" or not freq_ok or not excit_ok or tripped
        # Critères de synchronisation affichés dans l'étape 6
        _S_crit = {"fontFamily": "Share Tech Mono", "fontSize": "9px"}
        sync_criteria_children = html.Div([
            html.Div([
                html.Span("✅ " if excit_ok else "❌ "),
                html.Span(f"Excitation : {avr_mode_snap}",
                          style={"color": "#22c55e" if excit_ok else "#ef4444"}),
            ], style=_S_crit),
            html.Div([
                html.Span("✅ " if freq_ok else "❌ "),
                html.Span(f"Fréquence : {freq_snap:.2f} Hz (49.9–50.1 Hz)",
                          style={"color": "#22c55e" if freq_ok else "#f59e0b"}),
            ], style=_S_crit),
            html.Div([
                html.Span("ℹ️ "),
                html.Span("Cliquez « Armer synchronisation » quand vitesse nominale atteinte",
                          style={"color": "#64748b"}),
            ], style=_S_crit),
        ])

        # ── PID Power ──
        pid_err = state.get("pid_error")
        pid_out = state.get("pid_output")
        power_err_str = f"{pid_err:+.3f} MW" if pid_err is not None else "—"
        power_out_str = f"{pid_out:.1f} %"   if pid_out is not None else "—"

        # ── PID Speed (governor) — erreur/sortie non encore exposées, placeholder ──
        speed_err_str = "— RPM"
        speed_out_str = "— %"

        # ── Séquence ──
        seq_state    = state.get("sequence_state", "IDLE")
        seq_progress = state.get("sequence_progress")
        if seq_state in ("STARTING", "STOPPING") and seq_progress is not None:
            prog_pct  = round(seq_progress * 100)
            seq_wrap  = {"display": "block"}
            bar_style = {"height": "6px", "background": "#8b5cf6",
                         "borderRadius": "4px", "width": f"{prog_pct}%",
                         "transition": "width 0.5s ease"}
            seq_lbl   = f"{seq_state} — {prog_pct}%"
        else:
            seq_wrap  = {"display": "none"}
            bar_style = {"height": "6px", "background": "#8b5cf6",
                         "borderRadius": "4px", "width": "0%"}
            seq_lbl   = ""

        # ── Interlocks ──
        warnings = state.get("interlock_warnings", [])
        interlock_children = []
        for w in warnings:
            interlock_children.append(html.Div([
                html.Span("⚠ ", style={"color": "#f59e0b"}),
                html.Span(w, style={"fontSize": "11px", "fontFamily": "Share Tech Mono",
                                    "color": "#f59e0b"}),
            ], style={"marginBottom": "4px"}))
        if not warnings:
            interlock_children.append(html.Div([
                html.Span("✅ ", style={"color": "#22c55e"}),
                html.Span("Tous les interlocks OK", style={
                    "fontSize": "11px", "fontFamily": "Share Tech Mono", "color": "#22c55e",
                }),
            ]))
        vs  = state.get("valve_state", {})
        v1  = (vs.get("v1") or {}).get("current", 0)
        bp  = (vs.get("bp") or {}).get("current", 0)
        bp_ok = not (v1 > 10 and bp < 5)
        interlock_children.append(html.Div([
            html.Span("✅ " if bp_ok else "❌ ", style={"color": "#22c55e" if bp_ok else "#ef4444"}),
            html.Span("BP ≥ 5% si V1 > 10%", style={
                "fontSize": "11px", "fontFamily": "Share Tech Mono",
                "color": "#22c55e" if bp_ok else "#ef4444",
            }),
        ], style={"marginTop": "4px"}))

        # ── AVR warning ──
        # (avr_warn_style calculé dans la section Overlays ci-dessus)

        # ── AVR ──
        avr_vt   = state.get("avr_v_term")
        avr_efd  = state.get("avr_e_fd_pu")
        avr_cphi = state.get("avr_cosphi")
        avr_sat  = state.get("avr_saturated", False)
        avr_vt_str   = f"{avr_vt:.3f}"  if avr_vt  is not None else "—"
        avr_efd_str  = f"{avr_efd:.4f}" if avr_efd  is not None else "—"
        avr_cphi_str = f"{avr_cphi:.3f}" if avr_cphi is not None else "—"
        if avr_sat and avr_efd is not None:
            sat_label = "SAT MAX" if avr_efd >= 2.4 else "SAT MIN"
            sat_style = {"fontSize": "9px", "fontFamily": "Share Tech Mono", "fontWeight": "700",
                         "padding": "2px 6px", "borderRadius": "4px",
                         "color": "#ef4444", "background": "rgba(239,68,68,0.15)",
                         "border": "1px solid #ef4444"}
        else:
            sat_label = ""
            sat_style = {"fontSize": "9px", "padding": "2px 6px"}

        return (
            mode, mode_style,
            trip_banner_style, reset_btn_style,
            *step_classes,
            setpoints_style, valves_style, avr_style, reg_target_style,
            grid_sync_disabled, grid_disconnect_disabled,
            couple_disabled, sync_criteria_children,
            power_err_str, power_out_str,
            speed_err_str, speed_out_str,
            seq_wrap, bar_style, seq_lbl,
            interlock_children,
            avr_vt_str, avr_efd_str, avr_cphi_str, sat_label, sat_style,
            avr_warn_style,
        )

    # ── Sync cible régulation au chargement (non écrasé chaque seconde) ──
    @app.callback(
        Output("ctrl-regul-target", "value"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def sync_regul_target_on_load(pathname):
        if pathname != "/control":
            return no_update
        state, err = _get("/control/state")
        if err or not state:
            return no_update
        return state.get("regulation_target", "POWER")

    # ── Pré-remplir gains PID au chargement ─────────────────────────
    @app.callback(
        Output("ctrl-pid-power-kp",    "value"),
        Output("ctrl-pid-power-ki",    "value"),
        Output("ctrl-pid-power-kd",    "value"),
        Output("ctrl-pid-speed-kp",    "value"),
        Output("ctrl-pid-speed-ki",    "value"),
        Output("ctrl-pid-speed-kd",    "value"),
        Output("ctrl-pid-pressure-kp", "value"),
        Output("ctrl-pid-pressure-ki", "value"),
        Output("ctrl-pid-pressure-kd", "value"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def prefill_pid_gains(pathname):
        if pathname != "/control":
            return (no_update,) * 9
        state, err = _get("/control/state")
        if err or not state:
            return (no_update,) * 9
        return (
            state.get("pid_kp",          2.0),
            state.get("pid_ki",          0.5),
            state.get("pid_kd",          0.05),
            state.get("pid_speed_kp",    0.5),
            state.get("pid_speed_ki",    0.1),
            state.get("pid_speed_kd",    0.01),
            state.get("pid_pressure_kp", 1.0),
            state.get("pid_pressure_ki", 0.2),
            state.get("pid_pressure_kd", 0.02),
        )

    # ── Compteurs alarmes/trips dans le bandeau ──────────────────────
    @app.callback(
        Output("ctrl-banner-alarm-count", "children"),
        Output("ctrl-banner-trip-count",  "children"),
        Input("ctrl-log-interval", "n_intervals"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def update_banner_counters(n, pathname):
        if pathname != "/control":
            return no_update, no_update
        alarms_data, err = _get("/settings/alerts")
        if err or not alarms_data:
            return "—", "—"
        active = [a for a in alarms_data if not a.get("acknowledged")]
        trips  = [a for a in active if a.get("severity") in ("CRITICAL", "TRIP")]
        return str(len(active)), str(len(trips))

    # ── Dialogue confirmation AU ─────────────────────────────────────
    @app.callback(
        Output("ctrl-confirm-au", "displayed"),
        Input("ctrl-btn-au", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_au_dialog(n):
        return True

    # ── Exécution AU ─────────────────────────────────────────────────
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

    # ── Reset Trip ───────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-trip-status", "children"),
        Input("ctrl-btn-reset-trip", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def reset_trip(n, operator):
        if not n:
            return no_update
        data, err = _post("/control/emergency/reset",
                          {"operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok("✓ Trip réinitialisé.")

    # ── Changer mode ─────────────────────────────────────────────────
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
        State("ctrl-sp-power",       "value"),
        State("ctrl-sp-speed",       "value"),
        State("ctrl-sp-pressure",    "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_setpoints(n, power, speed, pressure, operator):
        if not n:
            return no_update
        sp = {}
        if power    is not None: sp["power_mw"]       = power
        if speed    is not None: sp["speed_rpm"]       = speed
        if pressure is not None: sp["pressure_hp_bar"] = pressure
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
        return _status_ok(f"✓ {' | '.join(parts)}")

    # ── Cible de régulation ──────────────────────────────────────────
    @app.callback(
        Output("ctrl-regul-target-status", "children"),
        Input("ctrl-btn-regul-target", "n_clicks"),
        State("ctrl-regul-target",   "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_regul_target(n, target, operator):
        if not n:
            return no_update
        data, err = _post("/control/regulation-target",
                          {"target": target, "operator": operator or "Opérateur"})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok(f"✓ Cible → {target}")

    # ── Affichage sliders vannes ─────────────────────────────────────
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

    # ── Appliquer vannes ─────────────────────────────────────────────
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
        results = data.get("results", {})
        rejets = [f"{k}: {v.get('message')}" for k, v in results.items() if not v.get("accepted")]
        if rejets:
            return _status_err("Refusé — " + " | ".join(rejets))
        return _status_ok(f"✓ V1={v1}% V2={v2}% V3={v3}% BP={vbp}%")

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
            data, err = _post("/control/sequence/start",
                              {"sequence": "start_turbine", "operator": op})
        elif triggered == "ctrl-btn-seq-stop":
            data, err = _post("/control/sequence/stop",
                              {"sequence": "stop_turbine", "operator": op})
        elif triggered == "ctrl-btn-seq-cancel":
            data, err = _post("/control/sequence/cancel", {"operator": op})
        else:
            return no_update
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok(f"✓ {data.get('message', 'OK')}")

    # ── Réglage PID (multi-boucle via onglets) ───────────────────────
    for _loop in ("power", "speed", "pressure"):
        def _make_pid_callback(loop_name):
            @app.callback(
                Output(f"ctrl-pid-{loop_name}-status", "children"),
                Input(f"ctrl-btn-pid-{loop_name}", "n_clicks"),
                State(f"ctrl-pid-{loop_name}-kp", "value"),
                State(f"ctrl-pid-{loop_name}-ki", "value"),
                State(f"ctrl-pid-{loop_name}-kd", "value"),
                State("store-operator-name",       "data"),
                prevent_initial_call=True,
            )
            def apply_pid_loop(n, kp, ki, kd, operator, _ln=loop_name):
                if not n:
                    return no_update
                if any(v is None for v in [kp, ki, kd]):
                    return _status_err("Renseignez Kp, Ki, Kd.")
                data, err = _post("/control/pid", {
                    "kp": kp, "ki": ki, "kd": kd,
                    "loop": _ln, "operator": operator or "Opérateur",
                })
                if err:
                    return _status_err(f"Erreur : {err}")
                return _status_ok(f"✓ PID {_ln} : Kp={kp} Ki={ki} Kd={kd}")
        _make_pid_callback(_loop)

    # ── AVR — mode + setpoints ───────────────────────────────────────
    @app.callback(
        Output("ctrl-avr-status", "children"),
        Input("ctrl-btn-avr", "n_clicks"),
        State("ctrl-avr-mode",       "value"),
        State("ctrl-avr-vset",       "value"),
        State("ctrl-avr-cosphi-set", "value"),
        State("ctrl-avr-efd-manual", "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_avr(n, mode, vset, cosphi_set, efd_manual, operator):
        if not n:
            return no_update
        op = operator or "Opérateur"
        # Bloquer le mode OFF quand la machine est couplée au réseau
        if mode == "OFF":
            state_check, _ = _get("/control/state")
            if (state_check or {}).get("machine_state") == "GRID_CONNECTED":
                return _status_err(
                    "⚠ Impossible de désexciter en GRID_CONNECTED — "
                    "découpler la machine avant."
                )
        _, err = _post("/control/avr/mode", {"mode": mode, "operator": op})
        if err:
            return _status_err(f"Mode AVR : {err}")
        if mode == "MANUAL" and efd_manual is not None:
            _post("/control/avr/manual", {"e_fd_pu": efd_manual, "operator": op})
        body = {}
        if vset       is not None: body["voltage_kv"] = vset
        if cosphi_set is not None: body["cosphi"]     = cosphi_set
        if body:
            _, err2 = _post("/control/avr/setpoint", {**body, "operator": op})
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
        return _status_ok(f"✓ K_A={ka}  T_A={ta} s")

    # ── Couplage réseau ──────────────────────────────────────────────
    @app.callback(
        Output("ctrl-grid-status", "children"),
        Input("ctrl-btn-grid-sync",       "n_clicks"),
        Input("ctrl-btn-grid-couple",     "n_clicks"),
        Input("ctrl-btn-grid-disconnect", "n_clicks"),
        State("store-operator-name",      "data"),
        prevent_initial_call=True,
    )
    def grid_action(n_sync, n_couple, n_disc, operator):
        op = operator or "Opérateur"
        triggered = ctx.triggered_id
        if triggered == "ctrl-btn-grid-sync":
            # Arme uniquement la synchronisation (EXCITED → SYNCHRONIZING)
            data, err = _post("/control/startup/sync-arm", {"operator": op})
        elif triggered == "ctrl-btn-grid-couple":
            # Couplage réseau avec vérifications f/U/excitation (SYNCHRONIZING → GRID_CONNECTED)
            data, err = _post("/control/startup/couple-grid", {"operator": op})
        elif triggered == "ctrl-btn-grid-disconnect":
            data, err = _post("/control/grid/disconnect", {"operator": op})
        else:
            return no_update
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok(f"✓ {(data or {}).get('message', 'OK')}")

    # ── Désurchauffeur ───────────────────────────────────────────────
    @app.callback(
        Output("ctrl-attemp-current-temp", "children"),
        Output("ctrl-attemp-injection",    "children"),
        Input("ctrl-state-interval",       "n_intervals"),
        Input("url",                       "pathname"),
        prevent_initial_call=False,
    )
    def update_attemperator_display(n, pathname):
        if pathname != "/control":
            return no_update, no_update
        data, err = _get("/control/attemperator")
        if err or not data:
            return "—", "—"
        # Affiche la T° HP mesurée (depuis le snapshot nominal) plutôt que la consigne
        t_actual = data.get("attemp_current_temp")
        if t_actual is None:
            snap, _ = _get("/data/current")
            t_actual = (snap or {}).get("temperature_hp")
        inj = data.get("attemp_injection_pct")
        t_str   = f"{t_actual:.0f} °C" if t_actual is not None else "—"
        inj_str = f"{inj:.1f} %"       if inj      is not None else "—"
        return t_str, inj_str

    @app.callback(
        Output("ctrl-attemp-status", "children"),
        Input("ctrl-btn-attemp", "n_clicks"),
        State("ctrl-attemp-enable",  "value"),
        State("ctrl-attemp-setpoint","value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_attemperator(n, enabled_val, setpoint, operator):
        if not n:
            return no_update
        op = operator or "Opérateur"
        enabled = "ON" in (enabled_val or [])
        _, err1 = _post("/control/attemperator/enabled",
                        {"enabled": enabled, "operator": op})
        if err1:
            return _status_err(f"Erreur enable : {err1}")
        if setpoint is not None:
            _, err2 = _post("/control/attemperator/setpoint",
                            {"setpoint_c": setpoint, "operator": op})
            if err2:
                return _status_err(f"Erreur setpoint : {err2}")
        state_txt = "actif" if enabled else "désactivé"
        sp_txt = f", consigne {setpoint}°C" if setpoint is not None else ""
        return _status_ok(f"✓ Désurchauffeur {state_txt}{sp_txt}")

    # ── Condenseur ───────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-cond-level-val",  "children"),
        Output("ctrl-cond-vacuum-val", "children"),
        Input("ctrl-state-interval",   "n_intervals"),
        Input("url",                   "pathname"),
        prevent_initial_call=False,
    )
    def update_condenser_display(n, pathname):
        if pathname != "/control":
            return no_update, no_update
        data, err = _get("/control/condenser")
        if err or not data:
            return "—", "—"
        lv  = data.get("condenser_level_pct")
        vac = data.get("condenser_vacuum_mbar")
        return (f"{lv:.1f}" if lv is not None else "—",
                f"{vac:.1f}" if vac is not None else "—")

    @app.callback(
        Output("ctrl-cond-status", "children"),
        Input("ctrl-btn-cond", "n_clicks"),
        State("ctrl-cond-level",     "value"),
        State("ctrl-cond-vacuum",    "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_condenser(n, level, vacuum, operator):
        if not n:
            return no_update
        op = operator or "Opérateur"
        msgs = []
        if level is not None:
            _, err = _post("/control/condenser/level-setpoint",
                           {"setpoint_pct": level, "operator": op})
            if err:
                return _status_err(f"Niveau : {err}")
            msgs.append(f"niveau {level}%")
        if vacuum is not None:
            _, err = _post("/control/condenser/vacuum-setpoint",
                           {"setpoint_mbar": vacuum, "operator": op})
            if err:
                return _status_err(f"Vide : {err}")
            msgs.append(f"vide {vacuum} mbar")
        if not msgs:
            return _status_err("Aucune consigne saisie.")
        return _status_ok(f"✓ Condenseur : {', '.join(msgs)}")

    # ── Protections Tier-1 ───────────────────────────────────────────
    @app.callback(
        Output("ctrl-protections-list", "children"),
        Input("ctrl-protections-interval", "n_intervals"),
        Input("url",                        "pathname"),
        prevent_initial_call=False,
    )
    def update_protections_list(n, pathname):
        if pathname != "/control":
            return no_update
        data, err = _get("/control/protections")
        if err or not data:
            return html.Div("Aucune protection récupérée.",
                            style={"fontSize": "11px", "color": "#64748b",
                                   "fontFamily": "Share Tech Mono"})

        _STATUS_COLOR = {
            "OK":       "#22c55e",
            "WARN":     "#f59e0b",
            "TRIP":     "#ef4444",
            "INHIBITED":"#64748b",
        }
        rows = []
        for prot in data.get("protections", []):
            name   = prot.get("name", "?")
            status = prot.get("status", "OK")
            inh    = prot.get("inhibited", False)
            color  = _STATUS_COLOR.get(status, "#94a3b8")
            rows.append(html.Div([
                html.Span(
                    "⛔" if status == "TRIP" else ("🔕" if inh else "🟢"),
                    style={"marginRight": "6px", "fontSize": "11px"},
                ),
                html.Span(_PROT_LABELS_FR.get(name, name), style={"fontSize": "10px", "fontFamily": "Share Tech Mono",
                                       "color": color, "flex": "1", "minWidth": "0"}),
                html.Button(
                    "Réactiver" if inh else "Inhiber",
                    id={"type": "ctrl-prot-inhibit-btn", "index": name},
                    n_clicks=0,
                    className="btn btn-outline",
                    style={"fontSize": "9px", "padding": "2px 6px",
                           "borderColor": "#64748b", "color": "#64748b",
                           "flexShrink": "0"},
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "4px",
                      "padding": "3px 0", "borderBottom": "1px solid #0f2744"}))
        return rows or html.Div("Aucune protection configurée.",
                                style={"fontSize": "11px", "color": "#64748b",
                                       "fontFamily": "Share Tech Mono"})

    @app.callback(
        Output({"type": "ctrl-prot-inhibit-btn", "index": MATCH}, "n_clicks"),
        Input({"type":  "ctrl-prot-inhibit-btn", "index": MATCH}, "n_clicks"),
        State({"type":  "ctrl-prot-inhibit-btn", "index": MATCH}, "children"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def toggle_protection_inhibit(n, btn_label, operator):
        if not n:
            return no_update
        name = ctx.triggered_id["index"]
        new_inhibited = (btn_label == "Inhiber")
        _post(
            f"/control/protections/{name}/inhibit",
            {"operator": operator or "Opérateur"},
            {"inhibited": "true" if new_inhibited else "false"},
        )
        return no_update

    # ── Phase de démarrage — timeline 7 étapes ──────────────────────
    _SPEED_NOMINAL   = 6435.0
    _SPEED_SYNC_THR  = 50.0
    _VTERM_TOL_KV    = 0.15
    _SEQ_DURATION_S  = 120.0
    _BP_ADMIT_TARGET = 100.0   # cible ouverture vapeur de barrage
    _BP_ADMIT_THR    = 80.0    # seuil bp_admit « ouverte »
    _BP_SPEED_THR    = 2500.0  # vitesse intermédiaire atteinte par la vapeur de barrage
    _V1_OPEN_TARGET  = 100.0    # cible ouverture V1 guidée
    _V1_OPEN_THR     = 5.0     # seuil V1 « ouverte »

    @app.callback(
        # Pastilles (className) — 7 étapes
        Output("ctrl-startup-pill-1", "className"),
        Output("ctrl-startup-pill-2", "className"),
        Output("ctrl-startup-pill-3", "className"),
        Output("ctrl-startup-pill-4", "className"),
        Output("ctrl-startup-pill-5", "className"),
        Output("ctrl-startup-pill-6", "className"),
        Output("ctrl-startup-pill-7", "className"),
        # Labels (className pour couleur) — 7 étapes
        Output("ctrl-startup-lbl-1", "className"),
        Output("ctrl-startup-lbl-2", "className"),
        Output("ctrl-startup-lbl-3", "className"),
        Output("ctrl-startup-lbl-4", "className"),
        Output("ctrl-startup-lbl-5", "className"),
        Output("ctrl-startup-lbl-6", "className"),
        Output("ctrl-startup-lbl-7", "className"),
        # Indicateurs textuels — 7 étapes
        Output("ctrl-startup-ind-1", "children"),
        Output("ctrl-startup-ind-2", "children"),
        Output("ctrl-startup-ind-3", "children"),
        Output("ctrl-startup-ind-4", "children"),
        Output("ctrl-startup-ind-5", "children"),
        Output("ctrl-startup-ind-6", "children"),
        Output("ctrl-startup-ind-7", "children"),
        # Détail pré-checks (step 1)
        Output("ctrl-startup-checks-detail", "children"),
        # Disabled des boutons d'action
        Output("ctrl-ph-btn-bp-admit", "disabled"),
        Output("ctrl-ph-btn-v1",       "disabled"),
        Output("ctrl-ph-btn-avr",      "disabled"),
        # Barres de progression par étape (style) — steps 2, 3, 4, 5
        Output("ctrl-startup-prog-2", "style"),
        Output("ctrl-startup-prog-3", "style"),
        Output("ctrl-startup-prog-4", "style"),
        Output("ctrl-startup-prog-5", "style"),
        # Bannière trip + barre globale + durée
        Output("ctrl-startup-trip-banner", "style"),
        Output("ctrl-startup-bar",         "style"),
        Output("ctrl-startup-elapsed",     "children"),
        Input("ctrl-state-interval",  "n_intervals"),
        Input("url",                   "pathname"),
        State("store-current-data",    "data"),
        prevent_initial_call=False,
    )
    def update_startup_phase(_n, pathname, current):
        n_out = 32  # 7 pills + 7 labels + 7 ind + 1 checks + 3 btn + 4 prog + 3 banner/bar/elapsed
        if pathname != "/control":
            return [no_update] * n_out

        state, err = _get("/control/state")
        if err or not state:
            return [no_update] * n_out

        ms        = state.get("machine_state", "STOPPED")
        mode      = state.get("control_mode", "MANUAL")
        tripped   = state.get("tripped", False)
        warnings  = state.get("interlock_warnings", [])
        valve_st  = state.get("valve_state") or {}
        v1        = valve_st.get("v1", {}).get("current", 0.0)
        bp_admit  = valve_st.get("bp_admit", {}).get("current", 0.0)
        avr_mode  = state.get("avr_mode", "OFF")
        avr_vt    = state.get("avr_v_term", 0.0) or 0.0
        avr_vset  = state.get("avr_setpoint", 10.5) or 10.5
        seq_prog  = state.get("sequence_progress") or 0.0
        phase     = state.get("startup_phase", "PRE_CHECKS")
        speed     = (current or {}).get("turbine_speed", 0.0) or 0.0
        power     = (current or {}).get("active_power", 0.0) or 0.0

        # ── Calcul statut de chaque étape — piloté par startup_phase ──
        _PHASE_ACTIVE_STEP = {
            "PRE_CHECKS":      1,
            "BARRAGE_OPENED":  2,
            "V1_OPENING":      3,
            "ACCELERATING":    4,
            "READY_TO_EXCITE": 5,
            "EXCITED":         6,   # step5 done, step6 active
            "SYNCHRONIZING":   6,
            "GRID_CONNECTED":  7,
        }
        active_step = _PHASE_ACTIVE_STEP.get(phase, 1)

        def _step_status(i: int) -> str:
            if tripped:
                return "tripped"
            if i < active_step:
                return "done"
            if i == active_step:
                return "active"
            return "future"

        step1 = _step_status(1)
        step2 = _step_status(2)
        step3 = _step_status(3)
        step4 = _step_status(4)
        step5 = _step_status(5)
        step6 = _step_status(6)
        step7 = _step_status(7)

        # Correction step1 : si des warnings existent, forcer active même si PRE_CHECKS
        if not tripped and step1 == "active" and len(warnings) == 0:
            step1 = "done"
        elif not tripped and step1 == "active" and len(warnings) > 0:
            pass  # reste active — pré-checks non validés

        # Cas EXCITED : step5 est done, step6 est active
        if phase == "EXCITED":
            step5 = "done"
            step6 = "active"

        # GRID_CONNECTED : toutes les étapes sont done sauf step7 si puissance > 0
        if phase == "GRID_CONNECTED" and not tripped:
            step1 = step2 = step3 = step4 = step5 = step6 = "done"
            step7 = "done" if power > 0.5 else "active"

        statuses = [step1, step2, step3, step4, step5, step6, step7]

        def pill_cls(s):
            return f"startup-pill startup-pill-{s}"

        def lbl_cls(s):
            css = "done" if s == "done" else "active" if s == "active" else "future"
            return f"startup-step-label startup-step-label-{css}"

        # ── Indicateurs textuels — avec icônes lock/check/active ──
        def _ind(status, done_txt, active_txt, locked_txt="🔒 Verrouillé — étape précédente requise"):
            if status == "done":
                return "✅ " + done_txt
            if status == "active":
                return active_txt
            if status == "tripped":
                return "⚡ TRIP"
            return locked_txt

        ind1 = _ind(step1,
                    done_txt   = f"OK • {len(warnings)} interlock(s)" if warnings else "OK — tous systèmes nominaux",
                    active_txt = f"⚠ {len(warnings)} interlock(s)" if warnings else "⚠ TRIP actif")

        bp_spd_pct = min(100, round(speed / _BP_SPEED_THR * 100))
        ind2 = _ind(step2,
                    done_txt   = f"BP = {bp_admit:.0f} % ✓ — {speed:.0f} RPM",
                    active_txt = f"BP = {bp_admit:.0f} % — vitesse {speed:.0f} / {_BP_SPEED_THR:.0f} RPM ({bp_spd_pct} %)")

        ind3 = _ind(step3,
                    done_txt   = f"V1 = {v1:.0f} % ✓",
                    active_txt = f"V1 = {v1:.0f} % (en ouverture…)")

        spd_pct = min(100, round(speed / _SPEED_NOMINAL * 100))
        ind4 = _ind(step4,
                    done_txt   = f"{speed:.0f} RPM ✓ — vitesse nominale atteinte",
                    active_txt = f"{speed:.0f} / {_SPEED_NOMINAL:.0f} RPM ({spd_pct} %)")

        if step5 == "done":
            ind5 = f"✅ V_term {avr_vt:.1f} kV — excité"
        elif step5 == "active":
            ind5 = "AVR OFF — activer VOLTAGE" if avr_mode == "OFF" \
                   else f"V_term {avr_vt:.1f} / {avr_vset:.1f} kV"
        elif step5 == "tripped":
            ind5 = "⚡ TRIP"
        else:
            ind5 = "🔒 Verrouillé — vitesse nominale requise"

        ind6 = _ind(step6,
                    done_txt   = "✓ Synchro armée — coupler au réseau",
                    active_txt = f"Δ vitesse = {abs(speed - _SPEED_NOMINAL):.0f} RPM — armer quand stable")

        ind7 = _ind(step7,
                    done_txt   = f"P = {power:.1f} MW — machine couplée",
                    active_txt = f"P = {power:.1f} MW")

        # ── Détail pré-checks (step 1) — appel GET /control/pre-check ──
        precheck_data, precheck_err = _get("/control/pre-check")
        precheck_all_ok = (precheck_data or {}).get("all_ok", False)

        if tripped:
            checks_detail = html.Div("⚡ TRIP actif — réinitialiser avant démarrage",
                                     style={"color": "#ef4444", "fontSize": "10px",
                                            "fontFamily": "Share Tech Mono"})
        elif precheck_err or not precheck_data:
            checks_detail = html.Div("⚠ Impossible de récupérer les pré-checks",
                                     style={"color": "#f59e0b", "fontSize": "10px",
                                            "fontFamily": "Share Tech Mono"})
        else:
            _S = {"fontFamily": "Share Tech Mono", "fontSize": "10px"}
            rows = []
            for c in precheck_data.get("checks", []):
                ok = c.get("ok", False)
                icon = "✅" if ok else "❌"
                val_str = f"{c.get('value', '')} {c.get('unit', '')}".strip()
                crit_str = c.get("crit", "")
                rows.append(html.Tr([
                    html.Td(icon, style={**_S, "width": "18px", "paddingRight": "4px"}),
                    html.Td(c.get("name", ""), style={**_S, "color": "#94a3b8", "paddingRight": "8px"}),
                    html.Td(val_str, style={**_S, "color": "#22c55e" if ok else "#ef4444",
                                            "fontWeight": "700", "paddingRight": "6px"}),
                    html.Td(f"({crit_str})", style={**_S, "color": "#475569"}),
                ]))
            all_ok_color = "#22c55e" if precheck_all_ok else "#ef4444"
            all_ok_msg = "✅ Tous les pré-checks OK — prêt à démarrer" if precheck_all_ok \
                         else "❌ Pré-checks non satisfaits — corriger avant de continuer"
            checks_detail = html.Div([
                html.Table(rows, style={"borderCollapse": "collapse", "width": "100%",
                                        "marginBottom": "4px"}),
                html.Div(all_ok_msg, style={**_S, "color": all_ok_color,
                                             "fontWeight": "700", "marginTop": "4px"}),
            ])

        # ── Gating séquentiel des boutons d'action — piloté par startup_phase ──
        btn_bp_disabled  = (phase != "PRE_CHECKS") or mode == "AUTO" or tripped \
                           or not precheck_all_ok
        btn_v1_disabled  = (phase != "BARRAGE_OPENED") or mode == "AUTO" or tripped \
                           or not precheck_all_ok
        btn_avr_disabled = (phase != "READY_TO_EXCITE") or tripped or not precheck_all_ok

        # ── Barres de progression contextuelles (visibles seulement si step active) ──
        def prog_style(active, pct, color):
            if not active:
                return {"display": "none"}
            pct = max(0, min(100, pct))
            return {
                "display": "block",
                "background": f"linear-gradient(to right, {color} {pct:.0f}%, #0f2744 {pct:.0f}%)",
                "height": "4px",
                "borderRadius": "2px",
                "marginTop": "5px",
                "transition": "background 0.4s ease",
            }

        prog2_pct = max(bp_admit / _BP_ADMIT_THR, speed / _BP_SPEED_THR) * 100
        prog2 = prog_style(step2 == "active", prog2_pct, "#f97316")
        prog3 = prog_style(step3 == "active", (v1 / _V1_OPEN_TARGET) * 100, "#f97316")
        prog4 = prog_style(step4 == "active", (speed / _SPEED_NOMINAL) * 100, "#22c55e")
        prog5_pct = (avr_vt / avr_vset) * 100 if avr_vset > 0 and avr_mode != "OFF" else 0
        prog5 = prog_style(step5 == "active", prog5_pct, "#a855f7")

        # ── Bandeau trip ──
        trip_style = {"display": "block"} if tripped else {"display": "none"}

        # ── Barre globale (temps écoulé) ──
        prog_pct  = round(seq_prog * 100)
        bar_style = {"background": "#22c55e", "height": "100%",
                     "transition": "width 0.5s ease", "width": f"{prog_pct}%"}
        elapsed_s = round(seq_prog * _SEQ_DURATION_S)
        elapsed   = f"{elapsed_s} / {int(_SEQ_DURATION_S)} s" if seq_prog > 0 else "—"

        return (
            [pill_cls(s) for s in statuses] +
            [lbl_cls(s)  for s in statuses] +
            [ind1, ind2, ind3, ind4, ind5, ind6, ind7,
             checks_detail,
             btn_bp_disabled, btn_v1_disabled, btn_avr_disabled,
             prog2, prog3, prog4, prog5,
             trip_style, bar_style, elapsed]
        )

    # ── Bouton action phase démarrage : Ouvrir vapeur barrage (bp_admit 100%) ──
    @app.callback(
        Output("ctrl-ph-bp-admit-status", "children"),
        Input("ctrl-ph-btn-bp-admit", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def ph_open_bp_admit(n, operator):
        if not n:
            return no_update
        op = operator or "Opérateur"
        data, err = _post("/control/startup/barrage", {"operator": op})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok("Vapeur barrage ouverte ✓")

    # ── Bouton action phase démarrage : Ouvrir V1 (15 %) ────────────
    @app.callback(
        Output("ctrl-ph-v1-status", "children"),
        Input("ctrl-ph-btn-v1", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def ph_open_v1(n, operator):
        if not n:
            return no_update
        op = operator or "Opérateur"
        data, err = _post("/control/startup/v1", {"operator": op})
        if err:
            return _status_err(f"Erreur : {err}")
        return _status_ok("V1 en ouverture ✓")

    # ── Bouton action phase démarrage : Activer AVR ──────────────────
    @app.callback(
        Output("ctrl-ph-avr-status", "children"),
        Input("ctrl-ph-btn-avr", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def ph_activate_avr(n, operator):
        if not n:
            return no_update
        op = operator or "Opérateur"
        _, err = _post("/control/startup/excite", {"operator": op})
        if err:
            return _status_err(f"Erreur AVR : {err}")
        return _status_ok("AVR VOLTAGE activé ✓")

    # ── Alarmes (acquittement + rafraîchissement) ────────────────────
    @app.callback(
        Output("ctrl-alarms-list", "children"),
        Input("ctrl-btn-ack-all",  "n_clicks"),
        Input("ctrl-log-interval", "n_intervals"),
        Input("url",               "pathname"),
        State("store-operator-name", "data"),
        prevent_initial_call=False,
    )
    def refresh_alarms(n_ack, n_int, pathname, operator):
        if pathname != "/control":
            return no_update
        if ctx.triggered_id == "ctrl-btn-ack-all" and n_ack:
            alarms_data, _ = _get("/settings/alerts")
            if alarms_data:
                for a in alarms_data:
                    if not a.get("acknowledged"):
                        _post(f"/settings/alerts/{a['id']}/acknowledge",
                              params={"operator": operator or "Opérateur"})
        alarms_data, err = _get("/settings/alerts")
        if err or not alarms_data:
            return html.Div("Aucune alarme récupérée.",
                            style={"fontSize": "11px", "color": "#64748b",
                                   "fontFamily": "Share Tech Mono"})
        active = [a for a in alarms_data if not a.get("acknowledged")]
        return alerts_panel(active)

    # ── Journal des commandes ────────────────────────────────────────
    @app.callback(
        Output("ctrl-commands-log", "children"),
        Input("ctrl-log-interval", "n_intervals"),
        Input("url",               "pathname"),
        prevent_initial_call=False,
    )
    def refresh_commands_log(n, pathname):
        if pathname != "/control":
            return no_update
        data, err = _get("/audit/operator-actions", params={"limit": 10})
        if err or not data:
            return html.Div("Aucune commande récente.",
                            style={"fontSize": "11px", "color": "#64748b",
                                   "fontFamily": "Share Tech Mono"})

        _ACTION_COLOR = {
            "MODE_CHANGE":        "#60a5fa",
            "SETPOINT_CHANGE":    "#22c55e",
            "VALVE_COMMAND":      "#f97316",
            "EMERGENCY_TRIP":     "#ef4444",
            "TRIP_RESET":         "#22c55e",
            "SEQUENCE_START":     "#8b5cf6",
            "SEQUENCE_CANCEL":    "#94a3b8",
            "SEQUENCE_COMPLETED": "#22c55e",
            "PID_TUNE":           "#f59e0b",
            "ALERT_ACK":          "#64748b",
            "AVR_MODE_CHANGE":    "#a855f7",
            "AVR_SETPOINT_CHANGE":"#a855f7",
            "AVR_GAINS_CHANGE":   "#a855f7",
            "AVR_EFD_MANUAL":     "#a855f7",
            "REGULATION_TARGET":  "#f59e0b",
            "GRID_SYNCHRONIZE":   "#22c55e",
            "GRID_DISCONNECT":    "#f97316",
            "ATTEMP_ENABLE":      "#22c55e",
            "ATTEMP_SETPOINT":    "#22c55e",
            "COND_LEVEL_SP":      "#22c55e",
            "COND_VACUUM_SP":     "#22c55e",
        }

        rows = []
        for a in data[:10]:
            ts    = (a.get("ts") or "")[:19].replace("T", " ")
            act   = a.get("action_type", "")
            tgt   = a.get("target", "")
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

        return rows or html.Div("Aucune commande.",
                                style={"fontSize": "11px", "color": "#64748b",
                                       "fontFamily": "Share Tech Mono"})

