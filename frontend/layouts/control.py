"""
layouts/control.py — Page Contrôle Commande GTA  (Cockpit 3 zones ISA-101)
Zone A : Supervision & Commande  |  Zone B : Régulation  |  Zone C : Sécurité & Traçabilité
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.sliders import slider_row


# ── Helpers mise en page ──────────────────────────────────────────────

def _section_header(title, color="var(--blue)"):
    return html.Div([
        html.Div(style={
            "width": "3px", "height": "14px", "flexShrink": "0",
            "background": color, "borderRadius": "2px",
        }),
        html.Span(title, style={
            "fontWeight": "600", "fontSize": "12px", "letterSpacing": "0.5px",
        }),
    ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "12px"})


def _card(*children, extra_style=None):
    style = {"marginBottom": "16px"}
    if extra_style:
        style.update(extra_style)
    return html.Div(list(children), className="card", style=style)


def _label(text):
    return html.Span(text, style={
        "fontSize": "10px", "color": "#94a3b8",
        "fontFamily": "Share Tech Mono", "letterSpacing": "1px",
        "display": "block", "marginBottom": "4px",
    })


def _subsection_divider(title, icon, color, first=False):
    return html.Div([
        html.Span(icon, style={"fontSize": "15px", "marginRight": "8px"}),
        html.Span(title, style={
            "fontWeight": "700", "fontSize": "12px",
            "letterSpacing": "2px", "color": color,
            "fontFamily": "Share Tech Mono",
        }),
    ], style={
        "marginTop": "0" if first else "20px", "marginBottom": "10px",
        "paddingBottom": "6px",
        "borderBottom": f"2px solid {color}44",
        "display": "flex", "alignItems": "center",
    })


def _overlay_style_active():
    return {}


def _overlay_style_greyed():
    return {"opacity": "0.4", "pointerEvents": "none", "filter": "grayscale(0.5)"}


# ── Bandeau sticky ────────────────────────────────────────────────────

def _machine_stepper():
    states = [
        ("STOPPED",       "ARRÊT"),
        ("ROLLING",       "DÉMARRAGE"),
        ("SYNCHRONIZING", "SYNCHRO"),
        ("GRID_CONNECTED","RÉSEAU"),
    ]
    items = []
    for i, (state_id, label) in enumerate(states):
        items.append(html.Div(label, id=f"ctrl-step-{state_id.lower()}", className="stepper-pill stepper-pill-future", **{"data-state": state_id}))
        if i < len(states) - 1:
            items.append(html.Span("›", className="stepper-chevron"))
    return html.Div(items, id="ctrl-machine-stepper", className="machine-stepper")


def _sticky_banner():
    return html.Div([
        # Ligne principale
        html.Div([
            # Gauche : mode + stepper
            html.Div([
                html.Div([
                    _label("MODE"),
                    html.Div(id="ctrl-mode-badge", children="MANUEL", style={
                        "fontSize": "16px", "fontWeight": "700",
                        "fontFamily": "Share Tech Mono", "letterSpacing": "2px",
                        "color": "#f97316",
                    }),
                ], style={"marginRight": "20px"}),
                _machine_stepper(),
            ], style={"display": "flex", "alignItems": "center", "flex": "1", "minWidth": 0}),

            # Centre : état + compteurs + opérateur + horloge
            html.Div([
                html.Div([
                    _label("ÉTAT"),
                    html.Div(id="ctrl-status-badge", children="—", style={
                        "fontSize": "13px", "fontWeight": "700",
                        "fontFamily": "Share Tech Mono", "color": "#00e676",
                    }),
                ], style={"marginRight": "16px"}),
                html.Div([
                    _label("ALARMES"),
                    html.Div(id="ctrl-banner-alarm-count", children="0", style={
                        "fontSize": "13px", "fontWeight": "700",
                        "fontFamily": "Share Tech Mono", "color": "#f59e0b",
                    }),
                ], style={"marginRight": "16px"}),
                html.Div([
                    _label("TRIPS"),
                    html.Div(id="ctrl-banner-trip-count", children="0", style={
                        "fontSize": "13px", "fontWeight": "700",
                        "fontFamily": "Share Tech Mono", "color": "#ef4444",
                    }),
                ], style={"marginRight": "20px"}),
                html.Div([
                    _label("OPÉRATEUR"),
                    html.Div(id="ctrl-banner-operator", children="—", style={
                        "fontSize": "11px", "fontFamily": "Share Tech Mono", "color": "#cbd5e1",
                    }),
                ], style={"marginRight": "16px"}),
                html.Div([
                    _label("HEURE"),
                    html.Div(id="ctrl-banner-clock", children="--:--:--", style={
                        "fontSize": "11px", "fontFamily": "Share Tech Mono", "color": "#64748b",
                    }),
                ]),
            ], style={"display": "flex", "alignItems": "center", "flexShrink": 0}),

            # Droite : trip banner + reset + AU
            html.Div([
                html.Div(id="ctrl-tripped-banner", style={"display": "none"}, children=[
                    html.Div("⚠ TRIP ACTIF — INSPECTION REQUISE", style={
                        "color": "#ef4444", "fontFamily": "Share Tech Mono",
                        "fontSize": "11px", "fontWeight": "700",
                        "border": "1px solid #ef4444", "borderRadius": "6px",
                        "padding": "4px 10px", "background": "rgba(239,68,68,0.1)",
                        "letterSpacing": "1px", "marginRight": "8px",
                    }),
                ]),
                html.Button(
                    "✅ Reset Trip",
                    id="ctrl-btn-reset-trip",
                    className="btn",
                    style={
                        "display": "none",
                        "fontSize": "11px", "padding": "6px 12px",
                        "background": "#22c55e", "border": "1px solid #22c55e",
                        "marginRight": "8px",
                    },
                ),
                html.Div(id="ctrl-trip-status", style={
                    "fontSize": "10px", "fontFamily": "Share Tech Mono",
                    "color": "#22c55e", "marginRight": "8px",
                }),
                html.Button(
                    "🛑 ARRÊT D'URGENCE",
                    id="ctrl-btn-au",
                    className="btn",
                    style={
                        "background": "#ef4444", "color": "white",
                        "border": "2px solid #ef4444",
                        "fontSize": "12px", "fontWeight": "700",
                        "padding": "8px 16px", "borderRadius": "8px",
                        "cursor": "pointer", "letterSpacing": "1px",
                        "fontFamily": "Share Tech Mono",
                        "boxShadow": "0 0 16px rgba(239,68,68,0.4)",
                    },
                ),
                dcc.ConfirmDialog(
                    id="ctrl-confirm-au",
                    message="⚠ CONFIRMER L'ARRÊT D'URGENCE ?\n\nCette action ferme instantanément la vanne V1 et bascule en mode MANUEL.\n\nContinuer ?",
                ),
                html.Div(id="ctrl-au-status", style={
                    "fontSize": "10px", "marginLeft": "8px",
                    "fontFamily": "Share Tech Mono",
                }),
            ], style={"display": "flex", "alignItems": "center", "flexShrink": 0, "marginLeft": "16px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
    ], className="ctrl-sticky-banner card", style={
        "marginBottom": "16px", "padding": "12px 16px",
        "border": "1px solid #1e3a5f",
    })


# ── ZONE A — Supervision & Commande ──────────────────────────────────

def _mode_card():
    return _card(
        _section_header("MODE D'EXPLOITATION", "#60a5fa"),
        html.Div([
            html.Div([
                _label("SÉLECTION MODE"),
                dcc.RadioItems(
                    id="ctrl-mode-radio",
                    options=[
                        {"label": "  MANUEL — commande directe des vannes", "value": "MANUAL"},
                        {"label": "  AUTO   — régulation PID sur consigne",  "value": "AUTO"},
                    ],
                    value="MANUAL",
                    labelStyle={"display": "block", "marginBottom": "8px",
                                "fontFamily": "Share Tech Mono", "fontSize": "11px",
                                "color": "#cbd5e1", "cursor": "pointer"},
                    inputStyle={"marginRight": "8px"},
                ),
            ], style={"flex": "1"}),
            html.Button(
                "↺ Appliquer",
                id="ctrl-btn-mode",
                className="btn btn-outline",
                style={"fontSize": "11px", "padding": "6px 12px", "alignSelf": "flex-end"},
            ),
        ], style={"display": "flex", "gap": "12px", "alignItems": "flex-start"}),
        html.Div(id="ctrl-mode-apply-status", style={
            "fontSize": "11px", "color": "#60a5fa",
            "fontFamily": "Share Tech Mono", "marginTop": "6px",
        }),
    )


def _sequences_card():
    return _card(
        _section_header("SÉQUENCES OPÉRATOIRES", "#8b5cf6"),
        html.Div([
            html.Button("▶ Start turbine", id="ctrl-btn-seq-start",
                        className="btn",
                        style={"background": "#22c55e", "border": "1px solid #22c55e",
                               "fontSize": "10px", "padding": "6px 10px",
                               "display": "block", "width": "100%", "marginBottom": "6px"}),
            html.Button("■ Stop normal",   id="ctrl-btn-seq-stop",
                        className="btn btn-outline",
                        style={"borderColor": "#f59e0b", "color": "#f59e0b",
                               "fontSize": "10px", "padding": "6px 10px",
                               "display": "block", "width": "100%", "marginBottom": "6px"}),
            html.Button("✕ Annuler",       id="ctrl-btn-seq-cancel",
                        className="btn btn-outline",
                        style={"borderColor": "#94a3b8", "color": "#94a3b8",
                               "fontSize": "10px", "padding": "6px 10px",
                               "display": "block", "width": "100%"}),
        ], style={"marginBottom": "10px"}),
        html.Div(id="ctrl-seq-progress-wrap", style={"display": "none"}, children=[
            _label("PROGRESSION"),
            html.Div(id="ctrl-seq-label", style={
                "fontSize": "10px", "color": "#8b5cf6",
                "fontFamily": "Share Tech Mono", "marginBottom": "4px",
            }),
            html.Div([
                html.Div(id="ctrl-seq-bar", style={
                    "height": "6px", "background": "#8b5cf6",
                    "borderRadius": "4px", "width": "0%",
                    "transition": "width 0.5s ease",
                }),
            ], style={"background": "#0f2744", "borderRadius": "4px", "overflow": "hidden"}),
        ]),
        html.Div(id="ctrl-seq-status", style={
            "fontSize": "10px", "color": "#8b5cf6",
            "fontFamily": "Share Tech Mono", "marginTop": "6px",
        }),
    )


def _startup_phase_card():
    _btn_style_base = {
        "fontSize": "10px", "padding": "4px 10px",
        "marginTop": "5px", "fontFamily": "Share Tech Mono",
    }

    def _action_btn(label, btn_id, color="#60a5fa", outline=False):
        if outline:
            s = {**_btn_style_base, "borderColor": color, "color": color}
            cls = "btn btn-outline"
        else:
            s = {**_btn_style_base, "background": color,
                 "border": f"1px solid {color}", "color": "#0a101a"}
            cls = "btn"
        return html.Button(label, id=btn_id, className=cls, style=s, disabled=True)

    def _action_status(status_id):
        return html.Div(id=status_id, style={
            "fontSize": "10px", "color": "#94a3b8",
            "fontFamily": "Share Tech Mono", "marginTop": "3px",
        })

    def _step(idx, label, connector=True, action=None, with_progress=False):
        content = [
            html.Div(label, id=f"ctrl-startup-lbl-{idx}",
                     className="startup-step-label startup-step-label-future"),
            html.Div(id=f"ctrl-startup-ind-{idx}",
                     className="startup-step-indicator", children="En attente"),
        ]
        if with_progress:
            content.append(html.Div(id=f"ctrl-startup-prog-{idx}",
                                    style={"display": "none"}))
        if action is not None:
            content.append(action)
        return html.Div([
            html.Div([
                html.Div(id=f"ctrl-startup-pill-{idx}",
                         className="startup-pill startup-pill-future"),
                html.Div(className="startup-connector") if connector else None,
            ], className="startup-step-graphic"),
            html.Div(content, className="startup-step-content"),
        ], className="startup-step")

    # ── Étape 1 : Pré-checks — info uniquement ──────────────────────
    step1 = _step(1, "Pré-checks",
                  action=html.Div(id="ctrl-startup-checks-detail",
                                  style={"marginTop": "4px"}))

    # ── Étape 2 : Vapeur de barrage (bp_admit) ───────────────────────
    step2 = _step(2, "Base Pression démarrage", with_progress=True,
                  action=html.Div([
                      _action_btn("↗ Ouvrir vapeur barrage (100 %)",
                                  "ctrl-ph-btn-bp-admit", "#f97316"),
                      _action_status("ctrl-ph-bp-admit-status"),
                  ]))

    # ── Étape 3 : Ouverture V1 ───────────────────────────────────────
    step3 = _step(3, "Ouverture V1", with_progress=True,
                  action=html.Div([
                      _action_btn("↗ Ouvrir V1 (100 %)", "ctrl-ph-btn-v1", "#f97316"),
                      _action_status("ctrl-ph-v1-status"),
                  ]))

    # ── Étape 4 : Accélération vitesse — passive (pas de bouton) ────
    step4 = _step(4, "Accélération vitesse", with_progress=True)

    # ── Étape 5 : Excitation alternateur ────────────────────────────
    step5 = _step(5, "Excitation alternateur", with_progress=True,
                  action=html.Div([
                      _action_btn("⚡ Activer AVR", "ctrl-ph-btn-avr", "#a855f7"),
                      _action_status("ctrl-ph-avr-status"),
                  ]))

    # ── Étape 6 : Synchronisation ────────────────────────────────────
    step6 = _step(6, "Synchronisation",
                  action=html.Div([
                      html.Button("🔄 Synchroniser réseau", id="ctrl-btn-grid-sync",
                                  className="btn",
                                  style={**_btn_style_base,
                                         "background": "#22c55e",
                                         "border": "1px solid #22c55e",
                                         "color": "#0a101a"},
                                  disabled=True),
                  ]))

    # ── Étape 7 : Couplage réseau ────────────────────────────────────
    step7 = _step(7, "Couplage réseau", connector=False,
                  action=html.Div([
                      html.Button("⏏ Découpler", id="ctrl-btn-grid-disconnect",
                                  className="btn btn-outline",
                                  style={**_btn_style_base,
                                         "borderColor": "#f97316", "color": "#f97316"},
                                  disabled=True),
                      html.Div(id="ctrl-grid-status", style={
                          "fontSize": "10px", "color": "#a855f7",
                          "fontFamily": "Share Tech Mono", "marginTop": "3px",
                      }),
                  ]))

    return _card(
        _section_header("PHASE DE DÉMARRAGE", "#22c55e"),
        html.Div(id="ctrl-startup-trip-banner", style={"display": "none"}, children=[
            html.Div("⚠ TRIP ACTIF — Reset requis avant démarrage",
                     className="startup-trip-banner"),
        ]),
        html.Div([step1, step2, step3, step4, step5, step6, step7],
                 className="startup-timeline"),
        html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0 6px"}),
        html.Div([
            html.Div(id="ctrl-startup-bar", className="startup-bar-fill"),
        ], className="startup-bar-track"),
        html.Div(id="ctrl-startup-elapsed", className="startup-elapsed", children="—"),
    )


def _valves_card():
    return _card(
        _section_header("COMMANDE VANNES — MANUEL", "#f97316"),
        html.Div(id="ctrl-valves-overlay", children=[
            html.Div("ADMISSION HP", style={"fontSize": "9px", "color": "#334155",
                "letterSpacing": "1.5px", "marginBottom": "4px", "fontFamily": "Share Tech Mono"}),
            slider_row("ctrl-v1", "V1 — Admission HP", 100, "#f97316",
                       "Contrôle 80% du débit HP"),
            html.Hr(style={"borderColor": "#0f2744", "margin": "8px 0"}),
            html.Div("ÉQUILIBRAGE", style={"fontSize": "9px", "color": "#334155",
                "letterSpacing": "1.5px", "marginBottom": "4px", "fontFamily": "Share Tech Mono"}),
            slider_row("ctrl-v2", "V2 — Équilibrage",  100, "#60a5fa", "~7% du débit"),
            slider_row("ctrl-v3", "V3 — Équilibrage",  100, "#60a5fa", "~7% du débit"),
            html.Hr(style={"borderColor": "#0f2744", "margin": "8px 0"}),
            html.Div("SORTIE BP", style={"fontSize": "9px", "color": "#334155",
                "letterSpacing": "1.5px", "marginBottom": "4px", "fontFamily": "Share Tech Mono"}),
            slider_row("ctrl-bp", "BP — Condenseur", 80, "#a78bfa",
                       "Min 5% si V1 > 10% (interlock)"),
            html.Div([
                html.Button("▶ Appliquer vannes", id="ctrl-btn-valves",
                            className="btn", style={"fontSize": "10px", "padding": "5px 12px"}),
            ], style={"textAlign": "right", "marginTop": "8px"}),
            html.Div(id="ctrl-valves-status", style={
                "fontSize": "10px", "color": "#f97316",
                "fontFamily": "Share Tech Mono", "marginTop": "6px",
            }),
        ]),
    )


# ── ZONE B — Régulation & Contrôle ───────────────────────────────────

def _setpoints_card():
    def sp_row(label, input_id, unit, placeholder, min_val, max_val):
        return html.Div([
            html.Div(label, style={"fontSize": "10px", "color": "#94a3b8",
                                   "fontFamily": "Share Tech Mono", "minWidth": "120px"}),
            dcc.Input(
                id=input_id, type="number", placeholder=placeholder,
                min=min_val, max=max_val, step=0.1,
                style={"width": "80px", "background": "#0f2744",
                       "border": "1px solid #1e3a5f", "borderRadius": "4px",
                       "color": "#e2e8f0", "padding": "4px 6px", "fontSize": "11px",
                       "fontFamily": "Share Tech Mono"},
            ),
            html.Span(unit, style={"fontSize": "10px", "color": "#f59e0b",
                                   "fontFamily": "Share Tech Mono", "marginLeft": "4px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "8px"})

    return _card(
        _section_header("CONSIGNES — MODE AUTO", "#f59e0b"),
        html.Div(id="ctrl-setpoints-overlay", children=[
            sp_row("Puissance active :", "ctrl-sp-power",    "MW",  "ex: 22.5", 0, 30),
            sp_row("Vitesse turbine :", "ctrl-sp-speed",     "RPM", "ex: 6435",  0, 7000),
            sp_row("Pression HP :",    "ctrl-sp-pressure",   "bar", "ex: 60.0",  0, 80),
            html.Div([
                html.Button("▶ Appliquer consignes", id="ctrl-btn-setpoints",
                            className="btn", style={"fontSize": "10px", "padding": "5px 12px"}),
            ], style={"textAlign": "right", "marginTop": "4px"}),
            html.Div(id="ctrl-setpoints-status", style={
                "fontSize": "10px", "color": "#f59e0b",
                "fontFamily": "Share Tech Mono", "marginTop": "6px",
            }),
        ]),
    )


def _regulation_target_card():
    return _card(
        _section_header("CIBLE DE RÉGULATION", "#f59e0b"),
        html.Div(id="ctrl-regul-target-overlay", children=[
            _label("BOUCLE ACTIVE"),
            dcc.RadioItems(
                id="ctrl-regul-target",
                options=[
                    {"label": "  PUISSANCE (MW)   — régulation P_MW via V1",  "value": "POWER"},
                    {"label": "  PRESSION (bar HP) — régulation P_HP via V1", "value": "PRESSURE"},
                ],
                value="POWER",
                labelStyle={"display": "block", "marginBottom": "6px",
                            "fontFamily": "Share Tech Mono", "fontSize": "11px",
                            "color": "#cbd5e1", "cursor": "pointer"},
                inputStyle={"marginRight": "8px"},
            ),
            html.Div([
                html.Button("▶ Appliquer", id="ctrl-btn-regul-target",
                            className="btn btn-outline",
                            style={"fontSize": "10px", "padding": "5px 12px",
                                   "borderColor": "#f59e0b", "color": "#f59e0b",
                                   "marginTop": "6px"}),
            ], style={"textAlign": "right"}),
            html.Div(id="ctrl-regul-target-status", style={
                "fontSize": "10px", "color": "#f59e0b",
                "fontFamily": "Share Tech Mono", "marginTop": "6px",
            }),
        ]),
    )


def _pid_tab_content(loop, label_kp, label_ki, label_kd,
                     default_kp, default_ki, default_kd, color="#f59e0b"):
    def gain_input(label, input_id, default):
        return html.Div([
            html.Span(label, style={"fontSize": "10px", "color": "#94a3b8",
                                    "fontFamily": "Share Tech Mono", "minWidth": "30px"}),
            dcc.Input(
                id=input_id, type="number", value=default, min=0, step=0.01,
                style={"width": "70px", "background": "#0f2744",
                       "border": "1px solid #1e3a5f", "borderRadius": "4px",
                       "color": "#e2e8f0", "padding": "3px 5px",
                       "fontSize": "11px", "fontFamily": "Share Tech Mono"},
            ),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px"})

    return html.Div([
        html.Div([
            gain_input("Kp", f"ctrl-pid-{loop}-kp", default_kp),
            gain_input("Ki", f"ctrl-pid-{loop}-ki", default_ki),
            gain_input("Kd", f"ctrl-pid-{loop}-kd", default_kd),
            html.Button("▶ Appliquer", id=f"ctrl-btn-pid-{loop}",
                        className="btn btn-outline",
                        style={"fontSize": "10px", "padding": "3px 8px",
                               "borderColor": color, "color": color}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px",
                  "flexWrap": "wrap", "marginBottom": "8px"}),
        html.Div([
            html.Div([
                html.Span("Erreur : ", style={"color": "#94a3b8", "fontSize": "10px",
                                               "fontFamily": "Share Tech Mono"}),
                html.Span(id=f"ctrl-pid-{loop}-error-val", children="—",
                          style={"color": color, "fontSize": "11px", "fontFamily": "Share Tech Mono"}),
            ]),
            html.Div([
                html.Span("Sortie PID : ", style={"color": "#94a3b8", "fontSize": "10px",
                                                   "fontFamily": "Share Tech Mono"}),
                html.Span(id=f"ctrl-pid-{loop}-output-val", children="—",
                          style={"color": color, "fontSize": "11px", "fontFamily": "Share Tech Mono"}),
            ]),
        ], style={"display": "flex", "gap": "20px", "marginBottom": "4px"}),
        html.Div(id=f"ctrl-pid-{loop}-status", style={
            "fontSize": "10px", "color": color,
            "fontFamily": "Share Tech Mono",
        }),
    ], style={"padding": "10px 0 4px 0"})


def _pid_card():
    return _card(
        _section_header("RÉGULATEURS PID", "#f59e0b"),
        dcc.Tabs(
            id="ctrl-pid-tabs",
            value="power",
            children=[
                dcc.Tab(
                    label="⚡ Puissance MW",
                    value="power",
                    children=_pid_tab_content("power", "Kp", "Ki", "Kd", 2.0, 0.5, 0.05),
                    style={"fontFamily": "Share Tech Mono", "fontSize": "10px",
                           "color": "#94a3b8", "padding": "4px 8px"},
                    selected_style={"fontFamily": "Share Tech Mono", "fontSize": "10px",
                                    "color": "#f59e0b", "background": "#0f2744",
                                    "borderTop": "2px solid #f59e0b", "padding": "4px 8px"},
                ),
                dcc.Tab(
                    label="🔄 Vitesse RPM",
                    value="speed",
                    children=_pid_tab_content("speed", "Kp", "Ki", "Kd", 0.5, 0.1, 0.01,
                                              color="#60a5fa"),
                    style={"fontFamily": "Share Tech Mono", "fontSize": "10px",
                           "color": "#94a3b8", "padding": "4px 8px"},
                    selected_style={"fontFamily": "Share Tech Mono", "fontSize": "10px",
                                    "color": "#60a5fa", "background": "#0f2744",
                                    "borderTop": "2px solid #60a5fa", "padding": "4px 8px"},
                ),
                dcc.Tab(
                    label="🔵 Pression HP",
                    value="pressure",
                    children=_pid_tab_content("pressure", "Kp", "Ki", "Kd", 1.0, 0.2, 0.02,
                                              color="#a78bfa"),
                    style={"fontFamily": "Share Tech Mono", "fontSize": "10px",
                           "color": "#94a3b8", "padding": "4px 8px"},
                    selected_style={"fontFamily": "Share Tech Mono", "fontSize": "10px",
                                    "color": "#a78bfa", "background": "#0f2744",
                                    "borderTop": "2px solid #a78bfa", "padding": "4px 8px"},
                ),
            ],
            style={"marginTop": "4px"},
        ),
    )


def _avr_card():
    def avr_input(label, input_id, default, min_val, max_val, step, unit=""):
        return html.Div([
            html.Span(label, style={"fontSize": "10px", "color": "#94a3b8",
                                    "fontFamily": "Share Tech Mono", "minWidth": "90px"}),
            dcc.Input(
                id=input_id, type="number", value=default,
                min=min_val, max=max_val, step=step,
                style={"width": "75px", "background": "#0f2744",
                       "border": "1px solid #1e3a5f", "borderRadius": "4px",
                       "color": "#e2e8f0", "padding": "3px 5px",
                       "fontSize": "11px", "fontFamily": "Share Tech Mono"},
            ),
            html.Span(unit, style={"fontSize": "10px", "color": "#a855f7",
                                   "fontFamily": "Share Tech Mono", "marginLeft": "4px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "7px"})

    return _card(
        _section_header("RÉGULATION TENSION / COS φ — AVR", "#a855f7"),
        html.Div(id="ctrl-avr-overlay", children=[
            # Indicateurs temps réel
            html.Div([
                html.Div([
                    html.Span("V_term : ", style={"color": "#94a3b8", "fontSize": "10px",
                                                   "fontFamily": "Share Tech Mono"}),
                    html.Span(id="ctrl-avr-vt-val", children="—",
                              style={"color": "#a855f7", "fontSize": "11px",
                                     "fontFamily": "Share Tech Mono"}),
                    html.Span(" kV", style={"color": "#64748b", "fontSize": "10px",
                                            "fontFamily": "Share Tech Mono"}),
                ]),
                html.Div([
                    html.Span("E_fd : ", style={"color": "#94a3b8", "fontSize": "10px",
                                                 "fontFamily": "Share Tech Mono"}),
                    html.Span(id="ctrl-avr-efd-val", children="—",
                              style={"color": "#a855f7", "fontSize": "11px",
                                     "fontFamily": "Share Tech Mono"}),
                    html.Span(" p.u.", style={"color": "#64748b", "fontSize": "10px",
                                              "fontFamily": "Share Tech Mono"}),
                ]),
                html.Div([
                    html.Span("cos φ : ", style={"color": "#94a3b8", "fontSize": "10px",
                                                  "fontFamily": "Share Tech Mono"}),
                    html.Span(id="ctrl-avr-cosphi-val", children="—",
                              style={"color": "#a855f7", "fontSize": "11px",
                                     "fontFamily": "Share Tech Mono"}),
                ]),
                html.Div(id="ctrl-avr-sat-badge", children="", style={
                    "fontSize": "9px", "fontFamily": "Share Tech Mono",
                    "fontWeight": "700", "padding": "2px 6px", "borderRadius": "4px",
                }),
            ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap",
                      "marginBottom": "10px", "padding": "6px 8px",
                      "background": "rgba(168,85,247,0.05)", "borderRadius": "6px",
                      "border": "1px solid rgba(168,85,247,0.15)"}),

            # Mode AVR
            html.Div([
                _label("MODE AVR"),
                dcc.RadioItems(
                    id="ctrl-avr-mode",
                    options=[
                        {"label": "  OFF",     "value": "OFF"},
                        {"label": "  TENSION", "value": "VOLTAGE"},
                        {"label": "  cos φ",   "value": "COSPHI"},
                        {"label": "  MANUEL",  "value": "MANUAL"},
                    ],
                    value="VOLTAGE",
                    inline=True,
                    labelStyle={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                                "color": "#cbd5e1", "cursor": "pointer", "marginRight": "10px"},
                    inputStyle={"marginRight": "4px"},
                ),
            ], style={"marginBottom": "8px"}),

            # Consignes
            avr_input("V_set (kV)  :", "ctrl-avr-vset",       10.5, 9.0, 12.0, 0.1, "kV"),
            avr_input("cos φ cible :", "ctrl-avr-cosphi-set",  0.85, 0.7, 1.0,  0.01, ""),
            avr_input("E_fd manuel :", "ctrl-avr-efd-manual",  1.0,  0.5, 2.5,  0.05, "p.u."),

            html.Div([
                html.Button("▶ Appliquer AVR", id="ctrl-btn-avr",
                            className="btn btn-outline",
                            style={"fontSize": "10px", "padding": "4px 10px",
                                   "borderColor": "#a855f7", "color": "#a855f7"}),
            ], style={"textAlign": "right", "marginBottom": "4px"}),
            html.Div(id="ctrl-avr-status", style={
                "fontSize": "10px", "color": "#a855f7",
                "fontFamily": "Share Tech Mono", "marginBottom": "6px",
            }),

            # Gains K_A / T_A
            html.Details([
                html.Summary("Réglage avancé K_A / T_A", style={
                    "fontSize": "11px", "color": "#a855f7",
                    "fontFamily": "Share Tech Mono", "cursor": "pointer",
                }),
                html.Div([
                    avr_input("K_A (gain) :", "ctrl-avr-ka", 200.0, 0, 1000, 10, ""),
                    avr_input("T_A (s) :",    "ctrl-avr-ta",   0.05, 0.001, 5.0, 0.01, "s"),
                    html.Button("▶ Appliquer gains", id="ctrl-btn-avr-gains",
                                className="btn btn-outline",
                                style={"fontSize": "10px", "padding": "3px 8px",
                                       "borderColor": "#a855f7", "color": "#a855f7",
                                       "marginTop": "4px"}),
                    html.Div(id="ctrl-avr-gains-status", style={
                        "fontSize": "10px", "color": "#a855f7",
                        "fontFamily": "Share Tech Mono", "marginTop": "4px",
                    }),
                ], style={"marginTop": "6px"}),
            ]),
        ]),
    )


def _grid_sync_card():
    return _card(
        _section_header("COUPLAGE RÉSEAU", "#a855f7"),
        html.Div([
            html.Button(
                "⚡ Synchroniser",
                id="ctrl-btn-grid-sync",
                className="btn",
                style={"background": "#22c55e", "border": "1px solid #22c55e",
                       "fontSize": "11px", "padding": "6px 12px", "flex": "1",
                       "marginRight": "8px"},
                disabled=True,
            ),
            html.Button(
                "⏏ Découpler",
                id="ctrl-btn-grid-disconnect",
                className="btn btn-outline",
                style={"borderColor": "#f97316", "color": "#f97316",
                       "fontSize": "11px", "padding": "6px 12px", "flex": "1"},
                disabled=True,
            ),
        ], style={"display": "flex", "marginBottom": "6px"}),
        html.Div(id="ctrl-grid-status", style={
            "fontSize": "10px", "color": "#a855f7",
            "fontFamily": "Share Tech Mono",
        }),
    )


def _attemperator_card():
    return _card(
        _section_header("DÉSURCHAUFFEUR", "#22c55e"),
        html.Div([
            html.Div([
                _label("T° ACTUELLE"),
                html.Div(id="ctrl-attemp-current-temp", children="—", style={
                    "fontSize": "16px", "fontWeight": "700",
                    "fontFamily": "Share Tech Mono", "color": "#22c55e",
                }),
            ], style={"marginRight": "20px"}),
            html.Div([
                _label("INJECTION"),
                html.Div(id="ctrl-attemp-injection", children="—", style={
                    "fontSize": "14px", "fontFamily": "Share Tech Mono", "color": "#60a5fa",
                }),
            ]),
        ], style={"display": "flex", "marginBottom": "10px", "padding": "6px 8px",
                  "background": "rgba(34,197,94,0.05)", "borderRadius": "6px",
                  "border": "1px solid rgba(34,197,94,0.15)"}),
        html.Div([
            dcc.Checklist(
                id="ctrl-attemp-enable",
                options=[{"label": "  Désurchauffeur actif", "value": "ON"}],
                value=[],
                labelStyle={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                            "color": "#cbd5e1", "cursor": "pointer"},
                inputStyle={"marginRight": "6px"},
            ),
        ], style={"marginBottom": "8px"}),
        html.Div([
            html.Span("Consigne T° :", style={"fontSize": "10px", "color": "#94a3b8",
                                              "fontFamily": "Share Tech Mono", "minWidth": "90px"}),
            dcc.Input(
                id="ctrl-attemp-setpoint", type="number", placeholder="ex: 440",
                min=300, max=520, step=1,
                style={"width": "70px", "background": "#0f2744",
                       "border": "1px solid #1e3a5f", "borderRadius": "4px",
                       "color": "#e2e8f0", "padding": "3px 5px",
                       "fontSize": "11px", "fontFamily": "Share Tech Mono"},
            ),
            html.Span("°C", style={"fontSize": "10px", "color": "#22c55e",
                                   "fontFamily": "Share Tech Mono", "marginLeft": "4px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "8px"}),
        html.Div([
            html.Button("▶ Appliquer", id="ctrl-btn-attemp",
                        className="btn btn-outline",
                        style={"fontSize": "10px", "padding": "4px 10px",
                               "borderColor": "#22c55e", "color": "#22c55e"}),
        ], style={"textAlign": "right"}),
        html.Div(id="ctrl-attemp-status", style={
            "fontSize": "10px", "color": "#22c55e",
            "fontFamily": "Share Tech Mono", "marginTop": "4px",
        }),
    )


def _condenser_card():
    def cond_row(label, input_id, placeholder, min_val, max_val, step, unit, color):
        return html.Div([
            html.Span(label, style={"fontSize": "10px", "color": "#94a3b8",
                                    "fontFamily": "Share Tech Mono", "minWidth": "100px"}),
            dcc.Input(
                id=input_id, type="number", placeholder=placeholder,
                min=min_val, max=max_val, step=step,
                style={"width": "70px", "background": "#0f2744",
                       "border": "1px solid #1e3a5f", "borderRadius": "4px",
                       "color": "#e2e8f0", "padding": "3px 5px",
                       "fontSize": "11px", "fontFamily": "Share Tech Mono"},
            ),
            html.Span(unit, style={"fontSize": "10px", "color": color,
                                   "fontFamily": "Share Tech Mono", "marginLeft": "4px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "7px"})

    return _card(
        _section_header("CONDENSEUR", "#22c55e"),
        html.Div([
            html.Div([
                html.Span("Niveau hotwell : ", style={"fontSize": "10px", "color": "#94a3b8",
                                                       "fontFamily": "Share Tech Mono"}),
                html.Span(id="ctrl-cond-level-val", children="—",
                          style={"fontSize": "11px", "fontFamily": "Share Tech Mono",
                                 "color": "#22c55e"}),
                html.Span(" %", style={"fontSize": "10px", "color": "#64748b",
                                       "fontFamily": "Share Tech Mono"}),
            ]),
            html.Div([
                html.Span("Vide : ", style={"fontSize": "10px", "color": "#94a3b8",
                                            "fontFamily": "Share Tech Mono"}),
                html.Span(id="ctrl-cond-vacuum-val", children="—",
                          style={"fontSize": "11px", "fontFamily": "Share Tech Mono",
                                 "color": "#22c55e"}),
                html.Span(" mbar", style={"fontSize": "10px", "color": "#64748b",
                                          "fontFamily": "Share Tech Mono"}),
            ]),
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap",
                  "marginBottom": "10px", "padding": "6px 8px",
                  "background": "rgba(34,197,94,0.05)", "borderRadius": "6px",
                  "border": "1px solid rgba(34,197,94,0.15)"}),
        cond_row("Consigne niveau :", "ctrl-cond-level", "ex: 60", 10, 90, 1, "%", "#22c55e"),
        cond_row("Consigne vide :",   "ctrl-cond-vacuum", "ex: 60", 20, 150, 1, "mbar", "#22c55e"),
        html.Div([
            html.Button("▶ Appliquer", id="ctrl-btn-cond",
                        className="btn btn-outline",
                        style={"fontSize": "10px", "padding": "4px 10px",
                               "borderColor": "#22c55e", "color": "#22c55e"}),
        ], style={"textAlign": "right"}),
        html.Div(id="ctrl-cond-status", style={
            "fontSize": "10px", "color": "#22c55e",
            "fontFamily": "Share Tech Mono", "marginTop": "4px",
        }),
    )


# ── ZONE C — Sécurité & Traçabilité ──────────────────────────────────

def _commands_log_card():
    return _card(
        _section_header("DERNIÈRES COMMANDES", "#60a5fa"),
        html.Div(id="ctrl-commands-log", className="zone-c-journal", children=[
            html.Div("Chargement…", style={
                "fontSize": "11px", "color": "#64748b", "fontFamily": "Share Tech Mono",
            }),
        ]),
        dcc.Interval(id="ctrl-log-interval",   interval=5000, n_intervals=0),
        dcc.Interval(id="ctrl-state-interval", interval=1000, n_intervals=0),
        dcc.Interval(id="ctrl-protections-interval", interval=2000, n_intervals=0),
    )


def _interlocks_card():
    return _card(
        _section_header("INTERLOCKS & PERMISSIVES", "#ef4444"),
        html.Div(id="ctrl-interlocks-list", children=[
            html.Div("Chargement…", style={
                "fontSize": "11px", "color": "#64748b", "fontFamily": "Share Tech Mono",
            }),
        ]),
    )


def _protections_card():
    return _card(
        _section_header("PROTECTIONS AUTOMATIQUES", "#ef4444"),
        html.Div(id="ctrl-protections-list", children=[
            html.Div("Chargement…", style={
                "fontSize": "11px", "color": "#64748b", "fontFamily": "Share Tech Mono",
            }),
        ]),
    )


def _alarms_card():
    return _card(
        html.Div([
            _section_header("ALARMES ACTIVES", "#ef4444"),
            html.Button(
                "✓ Acquitter tout",
                id="ctrl-btn-ack-all",
                className="btn btn-outline",
                style={"fontSize": "10px", "padding": "3px 8px",
                       "borderColor": "#ef4444", "color": "#ef4444",
                       "marginLeft": "auto"},
            ),
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between"}),
        html.Div(id="ctrl-alarms-list"),
    )


# ── Layout principal ──────────────────────────────────────────────────

def layout():
    return html.Div([
        create_sidebar(active_path="/control"),
        html.Div([

            # Bandeau sticky full-width
            _sticky_banner(),

            # 3 zones
            html.Div([

                # ── ZONE A — Supervision & Commande (~28%) ───────────
                html.Div([
                    _mode_card(),
                    _sequences_card(),
                    _startup_phase_card(),
                    _valves_card(),
                ], style={"flex": "7 1 0", "minWidth": "0"}),

                # ── ZONE B — Régulation & Contrôle (~44%) ────────────
                html.Div([
                    _subsection_divider("THERMIQUE", "🔥", "#f59e0b", first=True),
                    _setpoints_card(),
                    _regulation_target_card(),
                    _pid_card(),

                    _subsection_divider("ÉLECTRIQUE", "⚡", "#a855f7"),
                    _avr_card(),

                    _subsection_divider("AUXILIAIRES", "⚙", "#22c55e"),
                    _attemperator_card(),
                    _condenser_card(),
                ], style={"flex": "11 1 0", "minWidth": "0"}),

                # ── ZONE C — Sécurité & Traçabilité (~28%) ───────────
                html.Div([
                    _commands_log_card(),
                    _interlocks_card(),
                    _protections_card(),
                    _alarms_card(),
                ], style={"flex": "7 1 0", "minWidth": "0"}),

            ], className="ctrl-3-zones",
               style={"display": "flex", "width": "100%", "gap": "16px", "alignItems": "flex-start"}),

        ], className="main-content"),
    ], className="main-content-wrap")
