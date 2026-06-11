"""
callbacks/cb_control.py — Callbacks page Contrôle Commande GTA (Cockpit 3 zones)
"""
import math
import requests
from dash import Input, Output, State, html, no_update, ctx, clientside_callback, ALL, MATCH
from config import BACKEND
from components.alert_banner import alert_item, alerts_panel

_session = requests.Session()

_GREYED = {"opacity": "0.4", "pointerEvents": "none", "filter": "grayscale(0.5)"}
_ACTIVE = {}

_STATE_ORDER = ["STOPPED", "ROLLING", "SYNCHRONIZING", "GRID_CONNECTED"]


def _fuse_state_badge(data: dict) -> tuple[str, str]:
    """Fusionne machine_state + startup_phase + status en un libellé/couleur d'état opérateur.
    Priorités : TRIP > état transitoire (STOPPED/ROLLING/SYNC) > alarme (DEGRADED/CRITICAL) > NORMAL.
    """
    status        = (data.get("status") or "NORMAL").upper()
    machine_state = (data.get("machine_state") or "GRID_CONNECTED").upper()
    startup_phase = (data.get("startup_phase") or "GRID_CONNECTED").upper()
    tripped       = bool(data.get("tripped", False))

    if tripped or status == "TRIPPED" or machine_state == "TRIPPED":
        return "AU/TRIP ACTIF", "#ef4444"
    if machine_state == "STOPPED":
        # machine_state reste STOPPED de BARRAGE_OPENED à V1_OPENING — afficher DÉMARRAGE
        if startup_phase in ("BARRAGE_OPENED", "ESV_OPENED", "V1_OPENING"):
            return "DÉMARRAGE", "#f59e0b"
        return "MACHINE ARRÊTÉE", "#64748b"
    if machine_state == "ROLLING":
        esv_open = bool(data.get("esv_open", True))
        if not esv_open:
            return "ARRÊT — COAST-DOWN", "#f97316"
        return "DÉMARRAGE", "#f59e0b"
    if machine_state == "SYNCHRONIZING":
        return "SYNCHRONISATION", "#a78bfa"
    if status == "CRITICAL":
        return "CRITIQUE", "#ef4444"
    if status == "DEGRADED":
        return "DÉGRADÉ", "#f59e0b"
    return "NORMAL", "#00e676"

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


_notif_counter = [0]


def _notify(title, message, kind="warning"):
    _notif_counter[0] += 1
    return {"title": title, "message": str(message), "kind": kind, "n": _notif_counter[0]}

def _notify_ok(message, title="Modification appliquée"):
    return _notify(title, message, "success")

def _post(path, json_body=None, params=None):
    try:
        r = _session.post(f"{BACKEND}{path}", json=json_body, params=params, timeout=5)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail") or r.text
            except ValueError:
                detail = r.text or f"HTTP {r.status_code}"
            return None, detail
        return r.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"Connexion impossible : {e}"


def _get(path, params=None):
    try:
        r = _session.get(f"{BACKEND}{path}", params=params, timeout=5)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail") or r.text
            except ValueError:
                detail = r.text or f"HTTP {r.status_code}"
            return None, detail
        return r.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"Connexion impossible : {e}"


def register(app):

    # ── Pop-up notification — affichage (DOM direct) ─────────────────
    clientside_callback(
        """
        function(data) {
            if (!data) return window.dash_clientside.no_update;
            var modal = document.getElementById('ctrl-notif-modal');
            var icon  = document.getElementById('ctrl-notif-icon');
            var title = document.getElementById('ctrl-notif-title');
            var msg   = document.getElementById('ctrl-notif-message');
            if (!modal) return window.dash_clientside.no_update;
            var icons  = {warning: '⚠', error: '⛔', info: 'ℹ', success: '✓'};
            var colors = {warning: '#f59e0b', error: '#ef4444', info: '#60a5fa', success: '#22c55e'};
            icon.textContent  = icons[data.kind]  || '⚠';
            title.textContent = data.title   || '';
            title.style.color = colors[data.kind] || '#f59e0b';
            msg.textContent   = data.message || '';
            modal.style.display = 'flex';
            return '';
        }
        """,
        Output("ctrl-notif-dummy", "children"),
        Input("ctrl-notif-store", "data"),
        prevent_initial_call=True,
    )

    # ── Pop-up notification — fermeture (bouton OK) ──────────────────
    clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            var modal = document.getElementById('ctrl-notif-modal');
            if (modal) modal.style.display = 'none';
            return '';
        }
        """,
        Output("ctrl-notif-dummy", "children", allow_duplicate=True),
        Input("ctrl-notif-ok", "n_clicks"),
        prevent_initial_call=True,
    )

    # ── Notification : machine totalement arrêtée alors que mode=AUTO ──
    @app.callback(
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Output("ctrl-prev-machine-state", "data"),
        Input("store-current-data", "data"),
        State("ctrl-prev-machine-state", "data"),
        prevent_initial_call=True,
    )
    def notify_stopped_in_auto(ws_data, prev_state):
        data          = ws_data or {}
        machine_state = data.get("machine_state")
        mode          = data.get("control_mode", "MANUAL")
        tripped       = data.get("tripped", False)
        prev          = prev_state or {}
        new_state     = {"machine_state": machine_state}

        # Transition fraîche vers STOPPED (hors arrêt d'urgence), mode encore AUTO
        if (machine_state == "STOPPED"
                and prev.get("machine_state") not in (None, "STOPPED")
                and not tripped):
            if mode == "AUTO":
                return _notify(
                    "Machine arrêtée",
                    "La machine est totalement arrêtée.\n\n"
                    "Le mode est toujours AUTO : passez en MANUEL pour accéder "
                    "au réglage de la durée de préchauffage du barrage avant "
                    "un nouveau démarrage.",
                    "info",
                ), new_state
            else:
                return _notify(
                    "Machine arrêtée",
                    "La machine est totalement arrêtée.\n\n"
                    "Mode MANUEL actif : vous pouvez lancer directement la "
                    "séquence de démarrage (barrage → ESV → V1 → excitation → "
                    "synchronisation → couplage).",
                    "info",
                ), new_state

        return no_update, new_state
    
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

    # ── Bootstrap : charge tous les snapshots statiques en 1 round-trip ──
    @app.callback(
        Output("store-control-bootstrap", "data"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def load_control_bootstrap(pathname):
        if pathname != "/control":
            return no_update
        data, err = _get("/control/bootstrap")
        return data or {}

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
        label, color = _fuse_state_badge(data)
        return label, {"fontSize": "13px", "fontWeight": "700",
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
        Output("ctrl-btn-cancel-sequence", "disabled"),
        Output("ctrl-sync-criteria",        "children"),
        # PID Power readouts
        Output("ctrl-pid-power-error-val",  "children"),
        Output("ctrl-pid-power-output-val", "children"),
        # PID Speed readouts
        Output("ctrl-pid-speed-error-val",  "children"),
        Output("ctrl-pid-speed-output-val", "children"),
        # Interlocks
        Output("ctrl-interlocks-list",      "children"),
        # AVR
        Output("ctrl-avr-vt-val",           "children"),
        Output("ctrl-avr-efd-val",          "children"),
        Output("ctrl-avr-cosphi-val",       "children"),
        Output("ctrl-avr-sat-badge",        "children"),
        Output("ctrl-avr-sat-badge",        "style"),
        Output("ctrl-avr-grid-warning",     "style"),
        Output("ctrl-avr-preview",          "children"),
        Output("ctrl-avr-preview",          "style"),
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
            # Pendant les phases de démarrage (barrage / ESV / V1), machine_state reste STOPPED
            # mais le rotor tourne — on affiche ROLLING comme étape active pour l'opérateur.
            startup_phase_raw = state.get("startup_phase", "PRE_CHECKS")
            if machine_state == "STOPPED" and startup_phase_raw in (
                "BARRAGE_OPENED", "ESV_OPENED", "V1_OPENING"
            ):
                effective_state = "ROLLING"
            else:
                effective_state = machine_state
            idx = _STATE_ORDER.index(effective_state) if effective_state in _STATE_ORDER else 0
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
        grid_sync_disabled       = startup_phase != "EXCITED" or tripped or mode == "AUTO"
        grid_disconnect_disabled = machine_state != "GRID_CONNECTED"
        # Couplage : disponible uniquement en phase SYNCHRONIZING avec excitation + fréquence OK
        freq_snap  = state.get("grid_frequency", 0.0) or 0.0
        freq_ok    = 49.8 <= freq_snap <= 50.2
        excit_ok   = avr_mode_snap != "OFF"
        couple_disabled = startup_phase != "SYNCHRONIZING" or not freq_ok or not excit_ok or tripped or mode == "AUTO"
        sequence_state_snap = state.get("sequence_state", "IDLE")
        manual_startup_in_progress = (
            mode == "MANUAL"
            and startup_phase != "PRE_CHECKS"
            and machine_state != "GRID_CONNECTED"
        )
        cancel_seq_disabled = tripped or not (
            sequence_state_snap == "STARTING" or manual_startup_in_progress
        )
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
                html.Span(f"Fréquence : {freq_snap:.2f} Hz (49.8 – 50.2 Hz)",
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

        # ── AVR preview (valeurs prévues post-couplage) ──
        _S_prev = {"fontFamily": "Share Tech Mono", "fontSize": "9px"}
        avr_preview_show = avr_mode_snap != "OFF" and machine_state in ("ROLLING", "SYNCHRONIZING")
        if avr_preview_show:
            _p_prev = state.get("setpoint_power_mw") or 0.0
            _cf_prev = state.get("avr_cosphi_set") or 0.85
            _cf_prev = max(0.01, min(0.9999, _cf_prev))
            _q_prev = round(_p_prev * math.tan(math.acos(_cf_prev)), 1) if _p_prev > 0 else 0.0
            avr_preview_children = html.Div([
                html.Div("— Prévision post-couplage —", style={
                    **_S_prev, "color": "#64748b", "marginBottom": "3px",
                    "letterSpacing": "0.5px", "textAlign": "center",
                }),
                html.Div([
                    html.Span("P cible : ", style={**_S_prev, "color": "#64748b"}),
                    html.Span(f"{_p_prev:.1f} MW", style={**_S_prev, "color": "#22c55e"}),
                    html.Span("   Q prévue : ", style={**_S_prev, "color": "#64748b"}),
                    html.Span(f"{_q_prev:.1f} MVAR", style={**_S_prev, "color": "#22c55e"}),
                    html.Span("   cos φ : ", style={**_S_prev, "color": "#64748b"}),
                    html.Span(f"{_cf_prev:.2f}", style={**_S_prev, "color": "#22c55e"}),
                ]),
                html.Div("Circuit ouvert avant couplage — I = 0 A (normal)", style={
                    **_S_prev, "color": "#475569", "marginTop": "2px", "fontStyle": "italic",
                }),
            ])
            avr_preview_style = {
                "display": "block",
                "marginBottom": "8px", "padding": "5px 8px",
                "background": "rgba(34,197,94,0.06)",
                "border": "1px solid rgba(34,197,94,0.2)",
                "borderRadius": "4px",
            }
        else:
            avr_preview_children = []
            avr_preview_style = {"display": "none"}

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
            couple_disabled, cancel_seq_disabled, sync_criteria_children,
            power_err_str, power_out_str,
            speed_err_str, speed_out_str,
            interlock_children,
            avr_vt_str, avr_efd_str, avr_cphi_str, sat_label, sat_style,
            avr_warn_style,
            avr_preview_children, avr_preview_style,
        )

    # ── Sync cible régulation au chargement (non écrasé chaque seconde) ──
    @app.callback(
        Output("ctrl-regul-target", "value"),
        Input("store-control-bootstrap", "data"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def sync_regul_target_on_load(boot, pathname):
        if pathname != "/control":
            return no_update
        state = (boot or {}).get("state") or {}
        return state.get("regulation_target", "POWER") or no_update

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
        Input("store-control-bootstrap", "data"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def prefill_pid_gains(boot, pathname):
        if pathname != "/control":
            return (no_update,) * 9
        state = (boot or {}).get("state") or {}
        if not state:
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
        alarms_data, err = _get("/settings/alerts?limit=10&only_active=true")
        if err or not isinstance(alarms_data, list):
            return "—", "—"
        trips = [a for a in alarms_data if (a.get("severity") or "").upper() in ("CRITICAL", "TRIP")]
        return str(len(alarms_data)), str(len(trips))

    # ── Pop-up confirmation AU — ouverture (clic bouton AU) ───────────
    clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            var modal = document.getElementById('ctrl-au-confirm-modal');
            if (modal) modal.style.display = 'flex';
            return '';
        }
        """,
        Output("ctrl-au-confirm-dummy", "children"),
        Input("ctrl-btn-au", "n_clicks"),
        prevent_initial_call=True,
    )
    # ── Pop-up confirmation AU — Annuler ──────────────────────────────
    clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            var modal = document.getElementById('ctrl-au-confirm-modal');
            if (modal) modal.style.display = 'none';
            return '';
        }
        """,
        Output("ctrl-au-confirm-dummy", "children", allow_duplicate=True),
        Input("ctrl-au-confirm-no", "n_clicks"),
        prevent_initial_call=True,
    )
    # ── Pop-up confirmation AU — Confirmer (ferme le pop-up) ──────────
    clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            var modal = document.getElementById('ctrl-au-confirm-modal');
            if (modal) modal.style.display = 'none';
            return '';
        }
        """,
        Output("ctrl-au-confirm-dummy", "children", allow_duplicate=True),
        Input("ctrl-au-confirm-yes", "n_clicks"),
        prevent_initial_call=True,
    )

    # ── Exécution AU ─────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-au-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-au-confirm-yes", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def execute_au(n, operator):
        if not n:
            return no_update, no_update
        data, err = _post("/control/emergency/trip",
                          {"confirm": True, "operator": operator or "Opérateur"})
        if err:
            return _status_err(""), _notify("Arrêt d'urgence refusé", err, "error")
        return no_update, _notify_ok(
            "La machine a été arrêtée d'urgence. ESV fermée, V1/V2/V3 à 0%, mode basculé en MANUEL.",
            "Arrêt d'urgence exécuté",
        )

    # ── Reset Trip ───────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-trip-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-reset-trip", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def reset_trip(n, operator):
        if not n:
            return no_update, no_update
        data, err = _post("/control/emergency/reset",
                          {"operator": operator or "Opérateur"})
        if err:
            return _status_err(""), _notify("Reset Trip impossible", err, "warning")
        return no_update,  _notify_ok(
        "Le trip a été réinitialisé. La machine peut être redémarrée.",
        "Reset Trip",
    )

    # ── Changer mode ─────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-mode-apply-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-mode", "n_clicks"),
        State("ctrl-mode-radio",     "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_mode(n, mode, operator):
        if not n:
            return no_update, no_update
        data, err = _post("/control/mode", {"mode": mode, "operator": operator or "Opérateur"})
        if err:
            return _status_err(""), _notify("Changement de mode refusé", err)
        return no_update, _notify_ok(f"Mode {mode} appliqué", "Mode de pilotage")

    # ── Appliquer consignes ──────────────────────────────────────────
    @app.callback(
        Output("ctrl-setpoints-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-setpoints", "n_clicks"),
        State("ctrl-sp-power",       "value"),
        State("ctrl-sp-speed",       "value"),
        State("ctrl-sp-pressure",    "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_setpoints(n, power, speed, pressure, operator):
        if not n:
            return no_update, no_update
        sp = {}
        if power    is not None: sp["power_mw"]       = power
        if speed    is not None: sp["speed_rpm"]       = speed
        if pressure is not None: sp["pressure_hp_bar"] = pressure
        if not sp:
            return _status_err("Aucune consigne saisie."), no_update
        data, err = _post("/control/setpoints",
                          {"setpoints": sp, "operator": operator or "Opérateur"})
        if err:
            return _status_err(""), _notify("Consignes refusées", err)
        parts = []
        if power    is not None: parts.append(f"P={power} MW")
        if speed    is not None: parts.append(f"N={speed} RPM")
        if pressure is not None: parts.append(f"P_HP={pressure} bar")
        return no_update, _notify_ok(' | '.join(parts), "Consignes appliquées")

    # ── Cible de régulation ──────────────────────────────────────────
    @app.callback(
        Output("ctrl-regul-target-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-regul-target", "n_clicks"),
        State("ctrl-regul-target",   "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_regul_target(n, target, operator):
        if not n:
            return no_update, no_update
        data, err = _post("/control/regulation-target",
                          {"target": target, "operator": operator or "Opérateur"})
        if err:
            return _status_err(""), _notify("Bascule régulation impossible", err)
        return no_update, _notify_ok(f"Cible de régulation → {target}","Régulation")

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
        Output("ctrl-notif-store", "data", allow_duplicate=True),
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
            return no_update, no_update
        body = {"operator": operator or "Opérateur"}
        if v1  is not None: body["valve_v1"] = v1
        if v2  is not None: body["valve_v2"] = v2
        if v3  is not None: body["valve_v3"] = v3
        if vbp is not None: body["valve_bp"] = vbp
        data, err = _post("/control/valve", body)
        if err:
            return _status_err(""), _notify("Commande vannes refusée", err)
        results = data.get("results", {})
        rejets = [f"{k}: {v.get('message')}" for k, v in results.items() if not v.get("accepted")]
        if rejets:
            msg = " | ".join(rejets)
            return _status_err(""), _notify("Commande vannes refusée", msg)
        return no_update, _notify_ok(f"V1={v1}% V2={v2}% V3={v3}% BP={vbp}%", "Vannes")

    # ── Réglage PID (multi-boucle via onglets) ───────────────────────
    for _loop in ("power", "speed", "pressure"):
        def _make_pid_callback(loop_name):
            @app.callback(
                Output(f"ctrl-pid-{loop_name}-status", "children"),
                Output("ctrl-notif-store", "data", allow_duplicate=True),
                Input(f"ctrl-btn-pid-{loop_name}", "n_clicks"),
                State(f"ctrl-pid-{loop_name}-kp", "value"),
                State(f"ctrl-pid-{loop_name}-ki", "value"),
                State(f"ctrl-pid-{loop_name}-kd", "value"),
                State("store-operator-name",       "data"),
                prevent_initial_call=True,
            )
            def apply_pid_loop(n, kp, ki, kd, operator, _ln=loop_name):
                if not n:
                    return no_update, no_update
                if any(v is None for v in [kp, ki, kd]):
                    return _status_err("Renseignez Kp, Ki, Kd."), no_update
                data, err = _post("/control/pid", {
                    "kp": kp, "ki": ki, "kd": kd,
                    "loop": _ln, "operator": operator or "Opérateur",
                })
                if err:
                    return _status_err(""), _notify(f"PID {_ln} refusé", err)
                return no_update, _notify_ok(f"PID {_ln} : Kp={kp} Ki={ki} Kd={kd}", "Réglage PID")
        _make_pid_callback(_loop)

    # ── AVR — mode + setpoints ───────────────────────────────────────
    @app.callback(
        Output("ctrl-avr-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
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
            return no_update, no_update
        op = operator or "Opérateur"
        if mode == "OFF":
            state_check, _ = _get("/control/state")
            if (state_check or {}).get("machine_state") == "GRID_CONNECTED":
                msg = "Impossible de désexciter en GRID_CONNECTED — découpler la machine avant."
                return _status_err(""), _notify("AVR refusé", msg)
        _, err = _post("/control/avr/mode", {"mode": mode, "operator": op})
        if err:
            return _status_err(""), _notify("Mode AVR refusé", err)
        if mode == "MANUAL" and efd_manual is not None:
            _post("/control/avr/manual", {"e_fd_pu": efd_manual, "operator": op})
        body = {}
        if vset       is not None: body["voltage_kv"] = vset
        if cosphi_set is not None: body["cosphi"]     = cosphi_set
        if body:
            _, err2 = _post("/control/avr/setpoint", {**body, "operator": op})
            if err2:
                return _status_err(""), _notify("Consigne AVR refusée", err2)
        label = vset if mode == "VOLTAGE" else (cosphi_set if mode == "COSPHI" else efd_manual)
        return no_update, _notify_ok(f"AVR {mode} → {label}", "AVR")

    # ── AVR — gains K_A / T_A ────────────────────────────────────────
    @app.callback(
        Output("ctrl-avr-gains-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-avr-gains", "n_clicks"),
        State("ctrl-avr-ka",         "value"),
        State("ctrl-avr-ta",         "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_avr_gains(n, ka, ta, operator):
        if not n:
            return no_update, no_update
        if any(v is None for v in [ka, ta]):
            return _status_err("Renseignez K_A et T_A."), no_update
        data, err = _post("/control/avr/gains",
                          {"k_a": ka, "t_a": ta, "operator": operator or "Opérateur"})
        if err:
            return _status_err(""), _notify("Gains AVR refusés", err)
        return no_update, _notify_ok(f"K_A={ka}  T_A={ta} s", "Gains AVR")

    # ── Couplage réseau ──────────────────────────────────────────────
    @app.callback(
        Output("ctrl-grid-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
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
            data, err = _post("/control/startup/sync-arm", {"operator": op})
        elif triggered == "ctrl-btn-grid-couple":
            data, err = _post("/control/startup/couple-grid", {"operator": op})
        elif triggered == "ctrl-btn-grid-disconnect":
            data, err = _post("/control/grid/disconnect", {"operator": op})
        else:
            return no_update, no_update
        if err:
            return _status_err(""), _notify("Action réseau refusée", err)
        return no_update, _notify_ok((data or {}).get('message', 'OK'), "Réseau")

    # ── Annulation séquence de démarrage AUTO ─────────────────────────
    @app.callback(
        Output("ctrl-cancel-seq-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-cancel-sequence", "n_clicks"),
        State("store-operator-name",      "data"),
        prevent_initial_call=True,
    )
    def cancel_startup_sequence(n, operator):
        if not n:
            return no_update, no_update
        data, err = _post("/control/sequence/cancel", {"operator": operator or "Opérateur"})
        if err:
            return _status_err(""), _notify("Annulation refusée", err)
        return no_update, _notify_ok(
            (data or {}).get("message", "Séquence de démarrage annulée."),
            "Démarrage annulé",
        )
    # ── Désurchauffeur ───────────────────────────────────────────────
    @app.callback(
        Output("ctrl-attemp-current-temp", "children"),
        Output("ctrl-attemp-injection",    "children"),
        Input("ctrl-state-interval",       "n_intervals"),
        Input("store-control-bootstrap",   "data"),
        State("url",                       "pathname"),
        prevent_initial_call=False,
    )
    def update_attemperator_display(n, boot, pathname):
        if pathname != "/control":
            return no_update, no_update
        if ctx.triggered_id == "store-control-bootstrap" and boot:
            data = (boot or {}).get("attemperator") or {}
        else:
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
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-attemp", "n_clicks"),
        State("ctrl-attemp-enable",  "value"),
        State("ctrl-attemp-setpoint","value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_attemperator(n, enabled_val, setpoint, operator):
        if not n:
            return no_update, no_update
        op = operator or "Opérateur"
        enabled = "ON" in (enabled_val or [])
        _, err1 = _post("/control/attemperator/enabled",
                        {"enabled": enabled, "operator": op})
        if err1:
            return _status_err(""), _notify("Attempérateur refusé", err1)
        if setpoint is not None:
            _, err2 = _post("/control/attemperator/setpoint",
                            {"setpoint_c": setpoint, "operator": op})
            if err2:
                return _status_err(""), _notify("Consigne attempérateur refusée", err2)
        state_txt = "actif" if enabled else "désactivé"
        sp_txt = f", consigne {setpoint}°C" if setpoint is not None else ""
        return no_update, _notify_ok(f"Désurchauffeur {state_txt}{sp_txt}", "Désurchauffeur")

    # ── Condenseur ───────────────────────────────────────────────────
    @app.callback(
        Output("ctrl-cond-level-val",  "children"),
        Output("ctrl-cond-vacuum-val", "children"),
        Input("ctrl-state-interval",   "n_intervals"),
        Input("store-control-bootstrap", "data"),
        State("url",                   "pathname"),
        prevent_initial_call=False,
    )
    def update_condenser_display(n, boot, pathname):
        if pathname != "/control":
            return no_update, no_update
        if ctx.triggered_id == "store-control-bootstrap" and boot:
            data = (boot or {}).get("condenser") or {}
        else:
            data, err = _get("/control/condenser")
            if err or not data:
                return "—", "—"
        lv  = data.get("condenser_level_pct")
        vac = data.get("condenser_vacuum_mbar")
        return (f"{lv:.1f}" if lv is not None else "—",
                f"{vac:.1f}" if vac is not None else "—")

    @app.callback(
        Output("ctrl-cond-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-btn-cond", "n_clicks"),
        State("ctrl-cond-level",     "value"),
        State("ctrl-cond-vacuum",    "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def apply_condenser(n, level, vacuum, operator):
        if not n:
            return no_update, no_update
        op = operator or "Opérateur"
        msgs = []
        if level is not None:
            _, err = _post("/control/condenser/level-setpoint",
                           {"setpoint_pct": level, "operator": op})
            if err:
                return _status_err(""), _notify("Condenseur — niveau refusé", err)
            msgs.append(f"niveau {level}%")
        if vacuum is not None:
            _, err = _post("/control/condenser/vacuum-setpoint",
                           {"setpoint_mbar": vacuum, "operator": op})
            if err:
                return _status_err(""), _notify("Condenseur — vide refusé", err)
            msgs.append(f"vide {vacuum} mbar")
        if not msgs:
            return _status_err("Aucune consigne saisie."), no_update
        return no_update, _notify_ok(', '.join(msgs), "Condenseur")

    # ── Protections Tier-1 ───────────────────────────────────────────
    @app.callback(
        Output("ctrl-protections-list", "children"),
        Input("ctrl-protections-interval", "n_intervals"),
        Input("store-control-bootstrap",   "data"),
        State("url",                        "pathname"),
        prevent_initial_call=False,
    )
    def update_protections_list(n, boot, pathname):
        if pathname != "/control":
            return no_update
        if ctx.triggered_id == "store-control-bootstrap" and boot:
            data = (boot or {}).get("protections") or {}
        else:
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
        # Pastilles (className) — 8 étapes
        Output("ctrl-startup-pill-1", "className"),
        Output("ctrl-startup-pill-2", "className"),
        Output("ctrl-startup-pill-3", "className"),
        Output("ctrl-startup-pill-4", "className"),
        Output("ctrl-startup-pill-5", "className"),
        Output("ctrl-startup-pill-6", "className"),
        Output("ctrl-startup-pill-7", "className"),
        Output("ctrl-startup-pill-8", "className"),
        # Labels (className pour couleur) — 8 étapes
        Output("ctrl-startup-lbl-1", "className"),
        Output("ctrl-startup-lbl-2", "className"),
        Output("ctrl-startup-lbl-3", "className"),
        Output("ctrl-startup-lbl-4", "className"),
        Output("ctrl-startup-lbl-5", "className"),
        Output("ctrl-startup-lbl-6", "className"),
        Output("ctrl-startup-lbl-7", "className"),
        Output("ctrl-startup-lbl-8", "className"),
        # Indicateurs textuels — 8 étapes
        Output("ctrl-startup-ind-1", "children"),
        Output("ctrl-startup-ind-2", "children"),
        Output("ctrl-startup-ind-3", "children"),
        Output("ctrl-startup-ind-4", "children"),
        Output("ctrl-startup-ind-5", "children"),
        Output("ctrl-startup-ind-6", "children"),
        Output("ctrl-startup-ind-7", "children"),
        Output("ctrl-startup-ind-8", "children"),
        # Détail pré-checks (step 1)
        Output("ctrl-startup-checks-detail", "children"),
        # Disabled des boutons d'action
        Output("ctrl-ph-btn-bp-admit", "disabled"),
        Output("ctrl-ph-btn-esv",      "disabled"),
        Output("ctrl-ph-btn-v1",       "disabled"),
        Output("ctrl-ph-btn-avr",      "disabled"),
        # Barres de progression par étape (style) — steps 2, 4, 5, 6
        Output("ctrl-startup-prog-2", "style"),
        Output("ctrl-startup-prog-4", "style"),
        Output("ctrl-startup-prog-5", "style"),
        Output("ctrl-startup-prog-6", "style"),
        # Bannière trip + barre globale + durée
        Output("ctrl-startup-trip-banner", "style"),
        Input("ctrl-state-interval",  "n_intervals"),
        Input("url",                   "pathname"),
        State("store-current-data",    "data"),
        prevent_initial_call=False,
    )
    def update_startup_phase(_n, pathname, current):
        n_out = 34  # 8 pills + 8 labels + 8 ind + 1 checks + 4 btn + 4 prog + 3 banner/bar/elapsed
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
        phase     = state.get("startup_phase", "PRE_CHECKS")
        speed     = (current or {}).get("turbine_speed", 0.0) or 0.0
        power     = (current or {}).get("active_power", 0.0) or 0.0

        if phase == "PRE_CHECKS":
            precheck_data, precheck_err = _get("/control/pre-check")
            precheck_all_ok = (precheck_data or {}).get("all_ok", False)
        else:
            precheck_data, precheck_err = None, None
            precheck_all_ok = True

        # ── Calcul statut de chaque étape — piloté par startup_phase ──
        _PHASE_ACTIVE_STEP = {
            "PRE_CHECKS":      2,   # action live = ouvrir barrage (step2)
            "BARRAGE_OPENED":  2,   # action live = ouvrir ESV (step3)
            "ESV_OPENED":      4,   # action live = ouvrir V1 (step4)
            "V1_OPENING":      5,
            "ACCELERATING":    5,
            "READY_TO_EXCITE": 6,
            "EXCITED":         7,
            "SYNCHRONIZING":   7,
            "GRID_CONNECTED":  8,
        }
        active_step = _PHASE_ACTIVE_STEP.get(phase, 1)
        # Tant que les pré-checks ne sont pas validés, on reste bloqué sur step1
        if phase == "PRE_CHECKS" and not precheck_all_ok:
            active_step = 1

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
        step8 = _step_status(8)

        #Pendant BARRAGE_OPENED : step2 est encore "active" (préchauffage en cours)
        # mais step3 est aussi "active" car le bouton ESV apparaît dès que le timer arrive à 0.
        if phase == "BARRAGE_OPENED":
              step2 = "active"
              step3 = "future"  # ESV verrouillée tant que le préchauffage n'est pas fini
        # Correction step1 : si des warnings existent, forcer active même si PRE_CHECKS
        if not tripped and step1 == "active" and len(warnings) == 0:
            step1 = "done"
        elif not tripped and step1 == "active" and len(warnings) > 0:
            pass  # reste active — pré-checks non validés

        # Cas EXCITED : step6 est done, step7 est active
        if phase == "EXCITED":
            step6 = "done"
            step7 = "active"

        # GRID_CONNECTED : toutes les étapes sont done sauf step8 si puissance > 0
        if phase == "GRID_CONNECTED" and not tripped:
            step1 = step2 = step3 = step4 = step5 = step6 = step7 = "done"
            step8 = "done" if power > 0.5 else "active"

        statuses = [step1, step2, step3, step4, step5, step6, step7, step8]

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

        _ESV_MIN_SPEED = 2800.0

        bp_spd_pct = min(100, round(speed / _BP_SPEED_THR * 100))
        phase_remaining = state.get("phase_remaining_s")
        phase_total     = state.get("phase_total_s")
        if phase == "BARRAGE_OPENED" and phase_remaining is not None and phase_total:
            mm, ss = divmod(int(phase_remaining), 60)
            tot_mm, tot_ss = divmod(int(phase_total), 60)
            timer_txt = f" • ⏳ {mm:02d}:{ss:02d} / {tot_mm:02d}:{tot_ss:02d} avant ESV"
        else:
            timer_txt = ""
        ind2 = _ind(step2,
            done_txt   = f"BP = {bp_admit:.0f} % ✓ — {speed:.0f} RPM",
            active_txt = f"BP = {bp_admit:.0f} % — vitesse {speed:.0f} / {_BP_SPEED_THR:.0f} RPM ({bp_spd_pct} %){timer_txt}")

        esv_open = (current or {}).get("esv_open", False) or False
        esv_spd_pct = min(100, round(speed / _ESV_MIN_SPEED * 100))
        ind3 = _ind(step3,
                    done_txt   = "ESV ouverte ✓ — admission HP disponible",
                    active_txt = f"Vitesse {speed:.0f} / {_ESV_MIN_SPEED:.0f} RPM ({esv_spd_pct} %) avant ESV",
                    locked_txt = "🔒 Barrage requis")

        ind4 = _ind(step4,
                    done_txt   = f"V1 = {v1:.0f} % ✓",
                    active_txt = f"V1 = {v1:.0f} % (en ouverture…)",
                    locked_txt = "🔒 ESV requise")

        spd_pct = min(100, round(speed / _SPEED_NOMINAL * 100))
        ind5 = _ind(step5,
                    done_txt   = f"{speed:.0f} RPM ✓ — vitesse nominale atteinte",
                    active_txt = f"{speed:.0f} / {_SPEED_NOMINAL:.0f} RPM ({spd_pct} %)")

        if step6 == "done":
            ind6 = f"✅ V_term {avr_vt:.1f} kV — excité"
        elif step6 == "active":
            ind6 = "AVR OFF — activer VOLTAGE" if avr_mode == "OFF" \
                   else f"V_term {avr_vt:.1f} / {avr_vset:.1f} kV"
        elif step6 == "tripped":
            ind6 = "⚡ TRIP"
        else:
            ind6 = "🔒 Verrouillé — vitesse nominale requise"

        ind7 = _ind(step7,
                    done_txt   = "✓ Synchro armée — coupler au réseau",
                    active_txt = f"Δ vitesse = {abs(speed - _SPEED_NOMINAL):.0f} RPM — armer quand stable")

        ind8 = _ind(step8,
                    done_txt   = f"P = {power:.1f} MW — machine couplée",
                    active_txt = f"P = {power:.1f} MW")

        # ── Détail pré-checks (step 1) — appel GET /control/pre-check ──
        # precheck_data, precheck_err = _get("/control/pre-check")
        # precheck_all_ok = (precheck_data or {}).get("all_ok", False)

        if tripped:
            checks_detail = html.Div("⚡ TRIP actif — réinitialiser avant démarrage",
                                     style={"color": "#ef4444", "fontSize": "10px",
                                            "fontFamily": "Share Tech Mono"})
        elif phase != "PRE_CHECKS":
            checks_detail = html.Div("✅ Pré-checks validés — séquence engagée",
                                     style={"color": "#22c55e", "fontSize": "10px",
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
        btn_bp_disabled  = (phase != "PRE_CHECKS")    or mode == "AUTO" or tripped \
                           or not precheck_all_ok
        warmup_running   = (phase == "BARRAGE_OPENED"
                            and phase_remaining is not None
                            and phase_remaining > 0)
        btn_esv_disabled = (phase != "BARRAGE_OPENED") or mode == "AUTO" or tripped \
                           or speed < 2800 or warmup_running
        btn_v1_disabled  = (phase != "ESV_OPENED")    or mode == "AUTO" or tripped
        btn_avr_disabled = (phase != "READY_TO_EXCITE") or mode == "AUTO" or tripped

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
        prog4 = prog_style(step4 == "active", (v1 / _V1_OPEN_TARGET) * 100, "#f97316")
        prog5 = prog_style(step5 == "active", (speed / _SPEED_NOMINAL) * 100, "#22c55e")
        prog6_pct = (avr_vt / avr_vset) * 100 if avr_vset > 0 and avr_mode != "OFF" else 0
        prog6 = prog_style(step6 == "active", prog6_pct, "#a855f7")

        # ── Bandeau trip ──
        trip_style = {"display": "block"} if tripped else {"display": "none"}

        return (
            [pill_cls(s) for s in statuses] +
            [lbl_cls(s)  for s in statuses] +
            [ind1, ind2, ind3, ind4, ind5, ind6, ind7, ind8,
             checks_detail,
             btn_bp_disabled, btn_esv_disabled, btn_v1_disabled, btn_avr_disabled,
             prog2, prog4, prog5, prog6,
             trip_style]
        )

    # ── Slider durée préchauffage barrage : chargement initial ──────────
    @app.callback(
        Output("ctrl-barrage-warmup-slider", "value"),
        Output("ctrl-barrage-warmup-val",    "children"),
        Input("store-control-bootstrap", "data"),
        Input("url", "pathname"),
    )
    def init_barrage_warmup_slider(boot, pathname):
        if pathname != "/control":
            return no_update, no_update
        bw = (boot or {}).get("barrage_warmup") or {}
        if not bw:
            return 5, "5 min"
        value_min = round((bw.get("value_s", 300.0)) / 60.0)
        value_min = max(5, min(10, value_min))
        return value_min, f"{value_min} min"

    # ── Slider durée préchauffage barrage : désactivation hors PRE_CHECKS ──
    @app.callback(
        Output("ctrl-barrage-warmup-slider", "disabled"),
        Input("ctrl-state-interval",   "n_intervals"),
        Input("store-current-data",    "data"),
        State("url",                   "pathname"),
    )
    def update_warmup_slider_state(n, ws_data, pathname):
        if pathname != "/control":
            return no_update
        # startup_phase, tripped, control_mode sont dans GTAParameters → WebSocket
        data    = ws_data or {}
        mode    = data.get("control_mode",   "MANUAL")
        tripped = data.get("tripped",        False)
        phase   = data.get("startup_phase",  "PRE_CHECKS")
        # En AUTO, la séquence pilote le timer seule — on verrouille pour éviter les conflits.
        # En MANUAL, désactivé après la fin de la phase de préchauffage du barrage.
        return mode == "AUTO" or tripped or phase not in ("PRE_CHECKS", "BARRAGE_OPENED")

    # ── Slider durée préchauffage barrage : POST sur changement ─────────
    @app.callback(
        Output("ctrl-barrage-warmup-val", "children", allow_duplicate=True),
        Input("ctrl-barrage-warmup-slider", "value"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def on_barrage_warmup_change(value_min, operator):
        if value_min is None:
            return no_update
        seconds = float(value_min) * 60.0
        op = operator or "Opérateur"
        _post("/control/settings/barrage-warmup", {"seconds": seconds, "operator": op})
        return f"{value_min} min"

    # ── Bouton action phase démarrage : Ouvrir vapeur barrage (bp_admit 100%) ──
    @app.callback(
        Output("ctrl-ph-bp-admit-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-ph-btn-bp-admit", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def ph_open_bp_admit(n, operator):
        if not n:
            return no_update, no_update
        op = operator or "Opérateur"
        data, err = _post("/control/startup/barrage", {"operator": op})
        if err:
            return _status_err(""), _notify("Étape démarrage refusée", err)
        return no_update, _notify_ok("Vapeur barrage ouverte", "Démarrage")

    # ── Bouton action phase démarrage : Ouvrir ESV ──────────────────
    @app.callback(
        Output("ctrl-ph-esv-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-ph-btn-esv", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def ph_open_esv(n, operator):
        if not n:
            return no_update, no_update
        op = operator or "Opérateur"
        data, err = _post("/control/open-esv", {"operator": op})
        if err:
            return _status_err(""), _notify("Étape démarrage refusée", err)
        return no_update, _notify_ok(data.get("message", "ESV ouverte"), "Démarrage")
    # ── Bouton action phase démarrage : Ouvrir V1 ───────────────────
    @app.callback(
        Output("ctrl-ph-v1-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-ph-btn-v1", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def ph_open_v1(n, operator):
        if not n:
            return no_update, no_update
        op = operator or "Opérateur"
        data, err = _post("/control/startup/v1", {"operator": op})
        if err:
            return _status_err(""), _notify("Étape démarrage refusée", err)
        return no_update, _notify_ok("V1 en ouverture", "Démarrage")

    # ── Bouton action phase démarrage : Activer AVR ──────────────────
    @app.callback(
        Output("ctrl-ph-avr-status", "children"),
        Output("ctrl-notif-store", "data", allow_duplicate=True),
        Input("ctrl-ph-btn-avr", "n_clicks"),
        State("store-operator-name", "data"),
        prevent_initial_call=True,
    )
    def ph_activate_avr(n, operator):
        if not n:
            return no_update, no_update
        op = operator or "Opérateur"
        _, err = _post("/control/startup/excite", {"operator": op})
        if err:
            return _status_err(""), _notify("Activation AVR refusée", err)
        return no_update, _notify_ok("AVR VOLTAGE activé", "Démarrage")

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
            all_data, _ = _get("/settings/alerts?only_active=true")
            if all_data:
                for a in all_data:
                    _post(f"/settings/alerts/{a['id']}/acknowledge",
                          params={"operator": operator or "Opérateur"})
        alarms_data, err = _get("/settings/alerts?limit=10&only_active=true")
        if err or not isinstance(alarms_data, list):
            return html.Div("Aucune alarme récupérée.",
                            style={"fontSize": "11px", "color": "#64748b",
                                   "fontFamily": "Share Tech Mono"})
        return alerts_panel(alarms_data)

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
