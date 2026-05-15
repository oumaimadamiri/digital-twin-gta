"""
layouts/control.py — Page Contrôle Commande GTA
Pilotage actif : mode Manuel/Auto, consignes, PID, séquences, AU/Trip, interlocks, alarmes.
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.sliders import slider_row


# ── Helpers de mise en page ──────────────────────────────────────────

def _section_header(title, color="var(--blue)"):
    return html.Div([
        html.Div(style={
            "width": "3px", "height": "14px", "flexShrink": "0",
            "background": color, "borderRadius": "2px",
        }),
        html.Span(title, style={"fontWeight": "600", "fontSize": "12px", "letterSpacing": "0.5px"}),
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


# ── Carte header (statut + AU) ───────────────────────────────────────

def _header_card():
    return html.Div([
        # Badge mode
        html.Div([
            _label("MODE OPÉRATEUR"),
            html.Div(id="ctrl-mode-badge", children="MANUEL", style={
                "fontSize": "18px", "fontWeight": "700",
                "fontFamily": "Share Tech Mono", "letterSpacing": "2px",
                "color": "#f97316",
            }),
        ], style={"flex": "1"}),

        # Badge état GTA
        html.Div([
            _label("ÉTAT SYSTÈME"),
            html.Div(id="ctrl-status-badge", children="—", style={
                "fontSize": "16px", "fontWeight": "700",
                "fontFamily": "Share Tech Mono", "color": "#00e676",
            }),
        ], style={"flex": "1"}),

        # Tripped badge
        html.Div(id="ctrl-tripped-banner", style={"display": "none"}, children=[
            html.Div("⚠ TRIP ACTIF — INSPECTION REQUISE", style={
                "color": "#ef4444", "fontFamily": "Share Tech Mono",
                "fontSize": "12px", "fontWeight": "700",
                "border": "1px solid #ef4444", "borderRadius": "6px",
                "padding": "6px 12px", "background": "rgba(239,68,68,0.1)",
                "letterSpacing": "1px",
            }),
        ]),

        # Bouton AU
        html.Div([
            html.Button(
                "🛑 ARRÊT D'URGENCE",
                id="ctrl-btn-au",
                className="btn",
                style={
                    "background": "#ef4444", "color": "white",
                    "border": "2px solid #ef4444",
                    "fontSize": "13px", "fontWeight": "700",
                    "padding": "10px 20px", "borderRadius": "8px",
                    "cursor": "pointer", "letterSpacing": "1px",
                    "fontFamily": "Share Tech Mono",
                    "boxShadow": "0 0 16px rgba(239,68,68,0.4)",
                },
            ),
            dcc.ConfirmDialog(
                id="ctrl-confirm-au",
                message="⚠ CONFIRMER L'ARRÊT D'URGENCE ?\n\nCette action ferme instantanément la vanne V1 et bascule en mode MANUEL.\n\nContinuer ?",
            ),
            html.Div(id="ctrl-au-status", style={"fontSize": "11px", "marginTop": "6px",
                                                   "fontFamily": "Share Tech Mono"}),
        ]),
    ], className="card", style={
        "display": "flex", "alignItems": "center", "gap": "24px",
        "marginBottom": "16px", "padding": "16px 20px",
        "border": "1px solid #1e3a5f",
    })


# ── Carte Mode ───────────────────────────────────────────────────────

def _mode_card():
    return _card(
        _section_header("MODE D'EXPLOITATION", "#60a5fa"),
        html.Div([
            html.Div([
                _label("SÉLECTION MODE"),
                dcc.RadioItems(
                    id="ctrl-mode-radio",
                    options=[
                        {"label": "  MANUEL  — commande directe des vannes", "value": "MANUAL"},
                        {"label": "  AUTO    — régulation PID sur consigne puissance", "value": "AUTO"},
                    ],
                    value="MANUAL",
                    labelStyle={"display": "block", "marginBottom": "8px",
                                "fontFamily": "Share Tech Mono", "fontSize": "12px",
                                "color": "#cbd5e1", "cursor": "pointer"},
                    inputStyle={"marginRight": "8px"},
                ),
            ], style={"flex": "1"}),
            html.Div([
                html.Button(
                    "↺ Appliquer mode",
                    id="ctrl-btn-mode",
                    className="btn btn-outline",
                    style={"fontSize": "11px", "padding": "6px 14px"},
                ),
                html.Button(
                    "✅ Reset Trip",
                    id="ctrl-btn-reset-trip",
                    className="btn",
                    style={
                        "display": "none",
                        "fontSize": "11px", "padding": "6px 14px",
                        "background": "#22c55e", "border": "1px solid #22c55e",
                        "marginTop": "8px",
                    },
                ),
                html.Div(id="ctrl-trip-status", style={
                    "fontSize": "10px", "fontFamily": "Share Tech Mono", "marginTop": "4px",
                }),
            ], style={"display": "flex", "flexDirection": "column", "alignItems": "flex-end", "gap": "4px"}),
        ], style={"display": "flex", "alignItems": "flex-start", "gap": "16px"}),
        html.Div(id="ctrl-mode-apply-status", style={
            "fontSize": "11px", "color": "#60a5fa",
            "fontFamily": "Share Tech Mono", "marginTop": "8px",
        }),
    )


# ── Carte Consignes (Auto) ───────────────────────────────────────────

def _setpoints_card():
    def sp_row(label, input_id, unit, placeholder, min_val, max_val):
        return html.Div([
            html.Div(label, style={
                "fontSize": "11px", "color": "#94a3b8",
                "fontFamily": "Share Tech Mono", "minWidth": "130px",
            }),
            dcc.Input(
                id=input_id,
                type="number", placeholder=placeholder,
                min=min_val, max=max_val, step=0.1,
                style={
                    "width": "90px", "background": "#0f2744",
                    "border": "1px solid #1e3a5f", "borderRadius": "4px",
                    "color": "#e2e8f0", "padding": "4px 8px", "fontSize": "12px",
                    "fontFamily": "Share Tech Mono",
                },
            ),
            html.Span(unit, style={
                "fontSize": "10px", "color": "#60a5fa",
                "fontFamily": "Share Tech Mono", "marginLeft": "6px",
            }),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "10px"})

    return _card(
        _section_header("CONSIGNES — MODE AUTO", "#22c55e"),
        html.Div(id="ctrl-setpoints-overlay", children=[
            sp_row("Puissance active :", "ctrl-sp-power",    "MW",  "ex: 22.5", 0, 30),
            sp_row("Vitesse turbine :", "ctrl-sp-speed",    "RPM", "ex: 6435",  0, 7000),
            sp_row("Pression HP :",     "ctrl-sp-pressure", "bar", "ex: 60.0",  0, 80),
            html.Div([
                html.Button("▶ Appliquer consignes", id="ctrl-btn-setpoints",
                            className="btn", style={"fontSize": "11px", "padding": "6px 14px"}),
            ], style={"textAlign": "right", "marginTop": "4px"}),
            html.Div(id="ctrl-setpoints-status", style={
                "fontSize": "11px", "color": "#22c55e",
                "fontFamily": "Share Tech Mono", "marginTop": "8px",
            }),
        ]),
    )


# ── Carte Vannes Manuel ──────────────────────────────────────────────

def _valves_card():
    return _card(
        _section_header("COMMANDE VANNES — MODE MANUEL", "#f97316"),
        html.Div(id="ctrl-valves-overlay", children=[
            html.Div("ADMISSION HP", style={
                "fontSize": "9px", "color": "#334155",
                "letterSpacing": "1.5px", "marginBottom": "6px",
                "fontFamily": "Share Tech Mono",
            }),
            slider_row("ctrl-v1", "V1 — Admission HP", 100, "#f97316",
                       "Contrôle 80% du débit HP — régulation principale"),
            html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),
            html.Div("ÉQUILIBRAGE MÉCANIQUE", style={
                "fontSize": "9px", "color": "#334155",
                "letterSpacing": "1.5px", "marginBottom": "6px",
                "fontFamily": "Share Tech Mono",
            }),
            slider_row("ctrl-v2", "V2 — Équilibrage",  100, "#60a5fa",
                       "Répartition mécanique ~7% — pas d'effet thermo"),
            slider_row("ctrl-v3", "V3 — Équilibrage",  100, "#60a5fa",
                       "Répartition mécanique ~7% — pas d'effet thermo"),
            html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),
            html.Div("SORTIE VAPEUR BP", style={
                "fontSize": "9px", "color": "#334155",
                "letterSpacing": "1.5px", "marginBottom": "6px",
                "fontFamily": "Share Tech Mono",
            }),
            slider_row("ctrl-bp", "BP — Sortie condenseur", 80, "#a78bfa",
                       "Min 5% si V1 > 10% (interlock sécurité)"),
            html.Div([
                html.Button("▶ Appliquer vannes", id="ctrl-btn-valves",
                            className="btn", style={"fontSize": "11px", "padding": "6px 14px"}),
            ], style={"textAlign": "right", "marginTop": "8px"}),
            html.Div(id="ctrl-valves-status", style={
                "fontSize": "11px", "color": "#f97316",
                "fontFamily": "Share Tech Mono", "marginTop": "8px",
            }),
        ]),
    )


# ── Carte Séquences ──────────────────────────────────────────────────

def _sequences_card():
    return _card(
        _section_header("SÉQUENCES OPÉRATOIRES", "#8b5cf6"),
        html.Div([
            html.Button("▶ Start turbine",  id="ctrl-btn-seq-start",
                        className="btn",
                        style={"background": "#22c55e", "border": "1px solid #22c55e",
                               "fontSize": "11px", "padding": "7px 16px", "marginRight": "8px"}),
            html.Button("■ Stop normal",    id="ctrl-btn-seq-stop",
                        className="btn btn-outline",
                        style={"borderColor": "#f59e0b", "color": "#f59e0b",
                               "fontSize": "11px", "padding": "7px 16px", "marginRight": "8px"}),
            html.Button("✕ Annuler séquence", id="ctrl-btn-seq-cancel",
                        className="btn btn-outline",
                        style={"borderColor": "#94a3b8", "color": "#94a3b8",
                               "fontSize": "11px", "padding": "7px 16px"}),
        ], style={"marginBottom": "12px"}),
        html.Div(id="ctrl-seq-progress-wrap", style={"display": "none"}, children=[
            _label("PROGRESSION SÉQUENCE"),
            html.Div(id="ctrl-seq-label", style={
                "fontSize": "11px", "color": "#8b5cf6",
                "fontFamily": "Share Tech Mono", "marginBottom": "6px",
            }),
            html.Div([
                html.Div(id="ctrl-seq-bar", style={
                    "height": "8px", "background": "#8b5cf6",
                    "borderRadius": "4px", "width": "0%",
                    "transition": "width 0.5s ease",
                }),
            ], style={"background": "#0f2744", "borderRadius": "4px", "overflow": "hidden"}),
        ]),
        html.Div(id="ctrl-seq-status", style={
            "fontSize": "11px", "color": "#8b5cf6",
            "fontFamily": "Share Tech Mono", "marginTop": "8px",
        }),
    )


# ── Carte PID (réglage avancé) ───────────────────────────────────────

def _pid_card():
    def gain_input(label, input_id, default):
        return html.Div([
            html.Span(label, style={"fontSize": "10px", "color": "#94a3b8",
                                    "fontFamily": "Share Tech Mono", "minWidth": "30px"}),
            dcc.Input(
                id=input_id, type="number", value=default, min=0, step=0.01,
                style={
                    "width": "75px", "background": "#0f2744",
                    "border": "1px solid #1e3a5f", "borderRadius": "4px",
                    "color": "#e2e8f0", "padding": "4px 6px",
                    "fontSize": "12px", "fontFamily": "Share Tech Mono",
                },
            ),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"})

    return _card(
        _section_header("RÉGLAGE PID — RÉGULATEUR PUISSANCE", "#f59e0b"),
        html.Details([
            html.Summary("Réglage avancé Kp / Ki / Kd", style={
                "fontSize": "11px", "color": "#f59e0b",
                "fontFamily": "Share Tech Mono", "cursor": "pointer",
                "letterSpacing": "0.5px",
            }),
            html.Div([
                html.Div([
                    gain_input("Kp", "ctrl-pid-kp", 2.0),
                    gain_input("Ki", "ctrl-pid-ki", 0.5),
                    gain_input("Kd", "ctrl-pid-kd", 0.05),
                    html.Button("▶ Appliquer", id="ctrl-btn-pid",
                                className="btn btn-outline",
                                style={"fontSize": "10px", "padding": "4px 10px",
                                       "borderColor": "#f59e0b", "color": "#f59e0b"}),
                ], style={"display": "flex", "alignItems": "center", "gap": "12px",
                          "flexWrap": "wrap", "marginTop": "10px"}),
                html.Div([
                    html.Div([
                        html.Span("Erreur : ", style={"color": "#94a3b8", "fontSize": "10px",
                                                       "fontFamily": "Share Tech Mono"}),
                        html.Span(id="ctrl-pid-error-val", children="—",
                                  style={"color": "#f59e0b", "fontSize": "11px",
                                         "fontFamily": "Share Tech Mono"}),
                        html.Span(" MW", style={"color": "#64748b", "fontSize": "10px",
                                                "fontFamily": "Share Tech Mono"}),
                    ]),
                    html.Div([
                        html.Span("Sortie PID : ", style={"color": "#94a3b8", "fontSize": "10px",
                                                           "fontFamily": "Share Tech Mono"}),
                        html.Span(id="ctrl-pid-output-val", children="—",
                                  style={"color": "#f59e0b", "fontSize": "11px",
                                         "fontFamily": "Share Tech Mono"}),
                        html.Span(" %", style={"color": "#64748b", "fontSize": "10px",
                                               "fontFamily": "Share Tech Mono"}),
                    ]),
                ], style={"display": "flex", "gap": "24px", "marginTop": "8px"}),
                html.Div(id="ctrl-pid-status", style={
                    "fontSize": "10px", "color": "#f59e0b",
                    "fontFamily": "Share Tech Mono", "marginTop": "6px",
                }),
            ]),
        ]),
    )


# ── Carte AVR / Excitation ───────────────────────────────────────────

def _avr_card():
    def avr_input(label, input_id, default, min_val, max_val, step, unit=""):
        return html.Div([
            html.Span(label, style={"fontSize": "10px", "color": "#94a3b8",
                                    "fontFamily": "Share Tech Mono", "minWidth": "90px"}),
            dcc.Input(
                id=input_id, type="number", value=default,
                min=min_val, max=max_val, step=step,
                style={
                    "width": "80px", "background": "#0f2744",
                    "border": "1px solid #1e3a5f", "borderRadius": "4px",
                    "color": "#e2e8f0", "padding": "4px 6px",
                    "fontSize": "12px", "fontFamily": "Share Tech Mono",
                },
            ),
            html.Span(unit, style={"fontSize": "10px", "color": "#a855f7",
                                   "fontFamily": "Share Tech Mono", "marginLeft": "4px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "8px"})

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
                    "fontWeight": "700", "letterSpacing": "0.5px",
                    "padding": "2px 6px", "borderRadius": "4px",
                }),
            ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap",
                      "marginBottom": "12px", "padding": "8px",
                      "background": "rgba(168,85,247,0.05)",
                      "borderRadius": "6px", "border": "1px solid rgba(168,85,247,0.15)"}),

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
                                "color": "#cbd5e1", "cursor": "pointer", "marginRight": "12px"},
                    inputStyle={"marginRight": "4px"},
                ),
            ], style={"marginBottom": "10px"}),

            # Consignes
            avr_input("V_set (kV)  :", "ctrl-avr-vset",      10.5, 9.0, 12.0, 0.1,  "kV"),
            avr_input("cos φ cible :", "ctrl-avr-cosphi-set", 0.85, 0.7, 1.0,  0.01, ""),
            avr_input("E_fd manuel :", "ctrl-avr-efd-manual", 1.0,  0.5, 2.5,  0.05, "p.u."),

            html.Div([
                html.Button("▶ Appliquer AVR", id="ctrl-btn-avr",
                            className="btn btn-outline",
                            style={"fontSize": "10px", "padding": "5px 12px",
                                   "borderColor": "#a855f7", "color": "#a855f7"}),
            ], style={"textAlign": "right", "marginBottom": "6px"}),

            html.Div(id="ctrl-avr-status", style={
                "fontSize": "10px", "color": "#a855f7",
                "fontFamily": "Share Tech Mono", "marginBottom": "8px",
            }),

            # Réglage avancé K_a / T_a
            html.Details([
                html.Summary("Réglage avancé K_A / T_A", style={
                    "fontSize": "11px", "color": "#a855f7",
                    "fontFamily": "Share Tech Mono", "cursor": "pointer",
                    "letterSpacing": "0.5px",
                }),
                html.Div([
                    avr_input("K_A (gain) :", "ctrl-avr-ka", 200.0, 0, 1000, 10, ""),
                    avr_input("T_A (s) :",    "ctrl-avr-ta", 0.05,  0.001, 5.0, 0.01, "s"),
                    html.Button("▶ Appliquer gains", id="ctrl-btn-avr-gains",
                                className="btn btn-outline",
                                style={"fontSize": "10px", "padding": "4px 10px",
                                       "borderColor": "#a855f7", "color": "#a855f7",
                                       "marginTop": "6px"}),
                    html.Div(id="ctrl-avr-gains-status", style={
                        "fontSize": "10px", "color": "#a855f7",
                        "fontFamily": "Share Tech Mono", "marginTop": "4px",
                    }),
                ], style={"marginTop": "8px"}),
            ]),
        ]),
    )


# ── Carte Interlocks ─────────────────────────────────────────────────

def _interlocks_card():
    return _card(
        _section_header("INTERLOCKS & PERMISSIVES", "#ef4444"),
        html.Div(id="ctrl-interlocks-list", children=[
            html.Div("Chargement…", style={
                "fontSize": "11px", "color": "#64748b",
                "fontFamily": "Share Tech Mono",
            }),
        ]),
    )


# ── Carte Alarmes ────────────────────────────────────────────────────

def _alarms_card():
    return _card(
        html.Div([
            _section_header("ALARMES ACTIVES", "#ef4444"),
            html.Button(
                "✓ Acquitter tout",
                id="ctrl-btn-ack-all",
                className="btn btn-outline",
                style={"fontSize": "10px", "padding": "4px 10px",
                       "borderColor": "#ef4444", "color": "#ef4444",
                       "marginLeft": "auto"},
            ),
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between"}),
        html.Div(id="ctrl-alarms-list"),
    )


# ── Carte Journal Commandes ──────────────────────────────────────────

def _commands_log_card():
    return _card(
        _section_header("DERNIÈRES COMMANDES", "#60a5fa"),
        html.Div(id="ctrl-commands-log", children=[
            html.Div("Chargement…", style={
                "fontSize": "11px", "color": "#64748b",
                "fontFamily": "Share Tech Mono",
            }),
        ]),
        dcc.Interval(id="ctrl-log-interval",   interval=5000, n_intervals=0),
        dcc.Interval(id="ctrl-state-interval", interval=1000, n_intervals=0),
    )


# ── Layout principal ─────────────────────────────────────────────────

def layout():
    return html.Div([
        create_sidebar(active_path="/control"),
        html.Div([
            # Titre de page
            html.Div([
                html.Div("🎛", style={"fontSize": "24px", "marginRight": "12px"}),
                html.Div([
                    html.Div("CONTRÔLE COMMANDE", style={
                        "fontSize": "18px", "fontWeight": "700",
                        "fontFamily": "Share Tech Mono", "letterSpacing": "2px",
                        "color": "#e2e8f0",
                    }),
                    html.Div("Pilotage actif GTA — Manuel / Auto / Séquences / Sécurités",
                             style={"fontSize": "11px", "color": "#64748b",
                                    "fontFamily": "Share Tech Mono"}),
                ]),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "20px"}),

            # Header + AU
            _header_card(),

            # Contenu 2 colonnes
            html.Div([
                # Colonne gauche
                html.Div([
                    _mode_card(),
                    _setpoints_card(),
                    _avr_card(),
                    _sequences_card(),
                    _pid_card(),
                ], style={"flex": "1", "minWidth": "0"}),

                # Colonne droite
                html.Div([
                    _valves_card(),
                    _interlocks_card(),
                    _alarms_card(),
                    _commands_log_card(),
                ], style={"flex": "1", "minWidth": "0"}),
            ], style={"display": "flex", "gap": "16px", "alignItems": "flex-start"}),

        ], className="main-content"),
    ], className="app-shell")
