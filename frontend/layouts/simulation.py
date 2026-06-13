"""
layouts/simulation.py — Contrôle de la simulation : 5 vannes + 10 scénarios
"""
from dash import html, dcc
from components.sidebar import create_sidebar

import requests
from config import BACKEND
from components.gta_synoptic import create_gta_synoptic_static


# Session pour fetch initial
_session = requests.Session()

# (get_scenarios_from_api supprimé pour éviter le blocage au chargement)
_CRITICITE = {
    4:  ("CRITIQUE", "#ef4444"),
    9:  ("CRITIQUE", "#ef4444"),
    8:  ("MAJEUR",   "#f59e0b"),
    1:  ("MAJEUR",   "#f59e0b"),
    2:  ("MAJEUR",   "#f59e0b"),
    7:  ("MAJEUR",   "#f59e0b"),
    10: ("MAJEUR",   "#f59e0b"),
    3:  ("MODÉRÉ",   "#818cf8"),
    6:  ("MODÉRÉ",   "#818cf8"),
    5:  ("MODÉRÉ",   "#818cf8"),
}
def _info_icon(text):
    return html.Span([
        "i",
        html.Div(text, className="info-tooltip"),
    ], className="info-icon")

def _slider_row(valve_id, label, default, color, description):
    return html.Div([
        html.Div([
            html.Span(label, className="slider-label-text",
                      style={"color": color}),
            html.Div([
                html.Span(id=f"val-{valve_id}", className="slider-val-num"),
                html.Span("%", className="slider-val-unit"),
            ]),
        ], className="slider-label-row"),
        html.Div(description,
                 style={"fontSize": "9.5px", "color": "#334155",
                        "fontFamily": "Share Tech Mono", "marginBottom": "4px"}),
        dcc.Slider(
            id=f"slider-{valve_id}",
            min=0, max=100, step=1, value=default,
            marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
            className="custom-slider",
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ], className="slider-container")


def scenario_card(s):
    # Mapping depuis le format API backend
    ptype = s.get("perturbation_type", "unknown")
    if ptype == "ramp":
        icon, color, t_name = "📉", "#f59e0b", "RAMP"
    elif ptype == "step":
        icon, color, t_name = "⚡", "#ef4444", "STEP"
    elif ptype == "oscillation":
        icon, color, t_name = "〰", "#8b5cf6", "OSCIL"
    else:
        icon, color, t_name = "⚙", "#94a3b8", "OTHER"

    return html.Div([
        html.Div([
            html.Span(icon, className="scenario-icon",
                      style={"fontSize": "18px", "marginRight": "8px"}),
            html.Div([
                html.Div([
                    s.get("name", "N/A"),
                    _info_icon(s.get("description", "")),
                ], className="scenario-name",
                   style={"fontSize": "12px", "fontWeight": "600",
                          "display": "flex", "alignItems": "center", "gap": "6px"}),
                html.Div([
                    html.Span(f"#{s.get('id', 0)}", style={"color": "#334155",
                                                      "marginRight": "8px",
                                                      "fontSize": "10px"}),
                    html.Span(t_name,
                               style={"color": color, "fontSize": "10px",
                                      "background": f"rgba({_hex_to_rgb(color)},0.1)",
                                      "padding": "1px 6px", "borderRadius": "3px",
                                      "fontFamily": "Share Tech Mono"}),
                ]),
            ]),
        ], className="scenario-header",
           style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
        html.Button(
            "▶ DÉCLENCHER",
            id={"type": "btn-scenario", "index": s.get("id", 0)},
            value=s.get("name", "N/A"),
            className="btn btn-scenario",
            style={"--btn-color": color, "width": "100%"},
        ),
    ], className="card scenario-card",
       style={"--card-glow": color, "padding": "12px", "marginBottom": "8px"})


def _hex_to_rgb(hex_color):
    """Convertit #rrggbb en 'r,g,b' pour rgba()."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"

def _collapsible_header(title, toggle_id, accent_color="var(--blue)", is_open=True):
    return html.Div([
        html.Div([
            html.Div(style={
                "width": "3px", "height": "14px", "flexShrink": "0",
                "background": accent_color, "borderRadius": "2px",
            }),
            html.Span(title),
        ], className="collapse-title"),
        html.Span(
            "▼" if is_open else "▶",
            id=toggle_id,
            className="collapse-arrow",
        ),
    ],
    id=f"{toggle_id}-btn",
    n_clicks=0,
    className="collapse-header",
    )

def layout():
    return html.Div([
        create_sidebar(active_path="/simulation"),
        html.Div([
            # Synoptique simulation
            html.Div(
                className="synoptic-bleed",
                style={"position": "relative", "marginBottom": "20px", "minHeight": "520px"},
                children=[
                    html.Div(
                        id="gta-synoptic-sim",
                        children=[create_gta_synoptic_static(show_table=True, interactive=False)],
                        style={"minHeight": "520px"},
                    ),
                    html.Div([
                        html.Div("Scénario", className="card-title"),
                        html.Div(id="sim-scenario-panel"),
                        html.Button(
                            "■ Arrêter scénario",
                            id="btn-stop-scenario",
                            className="btn btn-outline",
                            style={
                                "display": "none",
                                "fontSize": "10px",
                                "padding": "5px 10px",
                                "borderColor": "#ef4444",
                                "color": "#ef4444",
                            },
                        ),
                    ], style={
                        "position":       "absolute",
                        "top":            "45px",
                        "right":          "12px",
                        "minWidth":       "240px",
                        "maxWidth":       "320px",
                        "width":          "auto",
                        "background":     "rgba(10,16,26,0.92)",
                        "border":         "1px solid #1e3a5f",
                        "borderRadius":   "8px",
                        "padding":        "12px",
                        "zIndex":         "10",
                        "backdropFilter": "blur(4px)",
                    }),
                ],
            ),
            dcc.Store(id="syn-sim-patch-tick", data=0),
            dcc.Store(id="sim-toast-store"),
            html.Span(id="sim-toast-dummy", style={"display": "none"}),

            # ── Bandeau Mode (Lecture / Bac à sable) ────────────────────────
            html.Div([
                html.Div([
                    html.Span("MODE : ", style={
                        "color": "#475569", "fontSize": "11px",
                        "fontFamily": "Share Tech Mono", "letterSpacing": "1px",
                    }),
                    html.Span(id="sandbox-mode-label", children="Lecture (données réelles)",
                              style={"fontWeight": "700", "fontSize": "12px",
                                     "color": "#64748b", "marginRight": "12px"}),
                    html.Span(
                        "Activez le bac à sable pour piloter les vannes et tester des "
                        "scénarios sans perturber la machine réelle.",
                        id="sandbox-mode-hint",
                        style={"fontSize": "10.5px", "color": "#475569",
                               "fontFamily": "Share Tech Mono"},
                    ),
                ], style={"flex": "1", "minWidth": "0"}),
                html.Button("🧪 Activer bac à sable", id="btn-sandbox-toggle",
                            className="btn btn-outline"),
            ], id="sandbox-banner", style={
                "display": "flex", "alignItems": "center", "justifyContent": "space-between",
                "gap": "16px", "padding": "10px 16px", "marginBottom": "14px",
                "background": "rgba(10,16,26,0.6)", "border": "1px solid #1e3a5f",
                "borderRadius": "8px", "flexWrap": "wrap",
            }),

            # ── Accordéon horizontal : 3 sections dans la même ligne ───────────
            html.Div([

                # ── Vannes ──────────────────────────────────────────────────────
                html.Div([
                    html.Div([
                        _collapsible_header("Contrôle des Vannes", "toggle-valves",
                                           accent_color="var(--orange)", is_open=False),
                        html.Div(id="collapse-valves", className="collapse-body",
                                 style={"display": "none"}, children=[

                            html.Div([
                                html.Div("ADMISSION HP", style={
                                    "fontSize": "9px", "color": "#334155",
                                    "letterSpacing": "1.5px", "marginBottom": "6px",
                                    "fontFamily": "Share Tech Mono",
                                }),
                                _slider_row("v1", "V1 — Admission HP", 100, "#f97316",
                                            "Contrôle 80% du débit HP — régulation principale"),
                            ]),
                            html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),
                            html.Div([
                                html.Div("ÉQUILIBRAGE MÉCANIQUE TURBINE", style={
                                    "fontSize": "9px", "color": "#334155",
                                    "letterSpacing": "1.5px", "marginBottom": "6px",
                                    "fontFamily": "Share Tech Mono",
                                }),
                                _slider_row("v2", "V2 — Équilibrage", 100, "#60a5fa",
                                            "Répartition effort mécanique ~7% — pas d'effet thermo"),
                                _slider_row("v3", "V3 — Équilibrage", 100, "#60a5fa",
                                            "Répartition effort mécanique ~7% — pas d'effet thermo"),
                            ]),
                            html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),
                            html.Div([
                                html.Div("CONDENSEUR", style={
                                    "fontSize": "9px", "color": "#334155",
                                    "letterSpacing": "1.5px", "marginBottom": "6px",
                                    "fontFamily": "Share Tech Mono",
                                }),
                                _slider_row("bp", "Vanne BP — Condenseur", 80, "#38bdf8",
                                            "Sortie BP vers condenseur · min 5% sécurité"),
                            ]),
                            html.Div([
                                html.Button("✔ Appliquer", id="btn-apply-valves",
                                            className="btn btn-success"),
                                html.Button("↺ Reset nominal", id="btn-reset",
                                            className="btn btn-danger",
                                            style={"marginLeft": "10px"}),
                            ], style={"marginTop": "14px"}),
                        ]),
                    ], className="card section-card"),
                ], id="section-valves-wrap", className="accordion-section"),

                # ── ESV / AVR / Lubrification (bac à sable) ──────────────────────
                html.Div([
                    html.Div([
                        _collapsible_header("ESV / AVR / Lubrification", "toggle-sandbox-ctrl",
                                           accent_color="var(--green)", is_open=False),
                        html.Div(id="collapse-sandbox-ctrl", className="collapse-body",
                                 style={"display": "none"}, children=[

                            html.Div([
                                html.Div("ESV — SOUPAPE D'ARRÊT HP", style={
                                    "fontSize": "9px", "color": "#334155",
                                    "letterSpacing": "1.5px", "marginBottom": "6px",
                                    "fontFamily": "Share Tech Mono",
                                }),
                                html.Div("Disponible pendant un scénario ou le bac à sable manuel.",
                                         style={"fontSize": "9.5px", "color": "#475569",
                                                "fontFamily": "Share Tech Mono", "marginBottom": "6px"}),
                                html.Div([
                                    html.Button("Ouvrir ESV", id="btn-esv-open",
                                                 className="btn btn-success",
                                                 style={"marginRight": "8px"}),
                                    html.Button("Fermer ESV", id="btn-esv-close",
                                                 className="btn btn-danger"),
                                ]),
                            ]),
                            html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),
                            html.Div([
                                html.Div("EXCITATION ALTERNATEUR (AVR) — SANDBOX SCÉNARIO", style={
                                    "fontSize": "9px", "color": "#334155",
                                    "letterSpacing": "1.5px", "marginBottom": "6px",
                                    "fontFamily": "Share Tech Mono",
                                }),
                                html.Div("Disponible pendant un scénario ou le bac à sable manuel.",
                                         style={"fontSize": "9.5px", "color": "#475569",
                                                "fontFamily": "Share Tech Mono", "marginBottom": "6px"}),
                                dcc.Dropdown(
                                    id="dd-avr-mode",
                                    options=[
                                        {"label": "OFF",     "value": "OFF"},
                                        {"label": "VOLTAGE", "value": "VOLTAGE"},
                                        {"label": "COSPHI",  "value": "COSPHI"},
                                        {"label": "MANUAL",  "value": "MANUAL"},
                                    ],
                                    value="VOLTAGE", clearable=False,
                                    className="custom-dropdown",
                                    style={"marginBottom": "8px"},
                                ),
                                html.Div([
                                    html.Label("Consigne tension (kV)",
                                               style={"fontSize": "9.5px", "color": "#94a3b8"}),
                                    dcc.Slider(id="slider-avr-voltage", min=9.0, max=12.0, step=0.05,
                                               value=10.5, marks=None, className="custom-slider",
                                               tooltip={"placement": "bottom", "always_visible": False}),
                                ], style={"marginBottom": "8px"}),
                                html.Div([
                                    html.Label("Consigne cos φ",
                                               style={"fontSize": "9.5px", "color": "#94a3b8"}),
                                    dcc.Slider(id="slider-avr-cosphi", min=0.7, max=1.0, step=0.01,
                                               value=0.85, marks=None, className="custom-slider",
                                               tooltip={"placement": "bottom", "always_visible": False}),
                                ], style={"marginBottom": "8px"}),
                                html.Div([
                                    html.Label("E_fd manuel (p.u.) — mode MANUAL",
                                               style={"fontSize": "9.5px", "color": "#94a3b8"}),
                                    dcc.Slider(id="slider-avr-efd", min=0.0, max=3.0, step=0.05,
                                               value=1.0, marks=None, className="custom-slider",
                                               tooltip={"placement": "bottom", "always_visible": False}),
                                ], style={"marginBottom": "8px"}),
                                html.Button("✔ Appliquer AVR", id="btn-apply-avr",
                                            className="btn btn-success"),
                            ]),
                            html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),
                            html.Div([
                                html.Div("LUBRIFICATION — OFFSETS SANDBOX", style={
                                    "fontSize": "9px", "color": "#334155",
                                    "letterSpacing": "1.5px", "marginBottom": "6px",
                                    "fontFamily": "Share Tech Mono",
                                }),
                                html.Div("Disponible pendant un scénario ou le bac à sable manuel.",
                                         style={"fontSize": "9.5px", "color": "#475569",
                                                "fontFamily": "Share Tech Mono", "marginBottom": "6px"}),
                                html.Div([
                                    html.Label("Δ Pression huile (bar)",
                                               style={"fontSize": "9.5px", "color": "#94a3b8"}),
                                    dcc.Slider(id="slider-lube-press-offset", min=-1.5, max=1.5, step=0.05,
                                               value=0.0, marks={-1.5: "-1.5", 0: "0", 1.5: "+1.5"},
                                               className="custom-slider",
                                               tooltip={"placement": "bottom", "always_visible": False}),
                                ], style={"marginBottom": "8px"}),
                                html.Div([
                                    html.Label("Δ Température huile (°C)",
                                               style={"fontSize": "9.5px", "color": "#94a3b8"}),
                                    dcc.Slider(id="slider-lube-temp-offset", min=-20, max=40, step=1,
                                               value=0, marks={-20: "-20", 0: "0", 40: "+40"},
                                               className="custom-slider",
                                               tooltip={"placement": "bottom", "always_visible": False}),
                                ], style={"marginBottom": "8px"}),
                                html.Button("✔ Appliquer Lubrification", id="btn-apply-lube",
                                            className="btn btn-success"),
                            ]),
                        html.Button("↺ Réinitialiser ESV/AVR/Lubrification", id="btn-reset-controls",
                             n_clicks=0, className="btn btn-secondary", style={"marginTop": "8px"}),
                        ]),
                    ], className="card section-card"),
                ], id="section-sandbox-ctrl-wrap", className="accordion-section"),

                # ── Scénarios ────────────────────────────────────────────────────
                html.Div([
                    html.Div([
                        _collapsible_header("Scénarios de Perturbation", "toggle-scenarios",
                                           accent_color="var(--purple)", is_open=False),
                        html.Div(id="collapse-scenarios", className="collapse-body",
                                 style={"display": "none"}, children=[
                            html.Div(
                                id="scenarios-list-container",
                                style={"maxHeight": "420px", "overflowY": "auto",
                                       "paddingRight": "4px"},
                                children=[html.Div("Chargement des scénarios...",
                                          style={"color": "#64748b", "fontFamily": "Share Tech Mono",
                                                 "padding": "20px"})],
                            ),
                        ]),
                    ], className="card section-card"),
                ], id="section-scenarios-wrap", className="accordion-section"),

                # ── Historique ───────────────────────────────────────────────────
                html.Div([
                    html.Div([
                        _collapsible_header("Historique des Scénarios", "toggle-history",
                                           accent_color="var(--blue-bright)", is_open=False),
                        html.Div(id="collapse-history", className="collapse-body",
                                 style={"display": "none"}, children=[
                            html.Div(id="scenario-history-list",
                                     className="history-container",
                                     style={"maxHeight": "300px", "overflowY": "auto"}),
                        ]),
                    ], className="card section-card"),
                ], id="section-history-wrap", className="accordion-section"),

            ], className="accordion-row"),

        ], className="page-content"),
    ], className="main-content-wrap")