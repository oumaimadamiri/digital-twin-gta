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
                html.Div(s.get("name", "N/A"), className="scenario-name",
                         style={"fontSize": "12px", "fontWeight": "600"}),
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


def layout():
    return html.Div([
        create_sidebar(active_path="/simulation"),
        html.Div([
            # Synoptique simulation
            html.Div(
                style={"position": "relative", "marginBottom": "20px"},
                children=[
                    html.Div(
                        id="gta-synoptic-sim",
                        children=[create_gta_synoptic_static()],
                    ),
                    html.Div([
                        html.Div("État Système", className="card-title"),
                        html.Div(id="sim-state-panel"),
                        html.Button(
                            "🛑 ARRÊTER SCÉNARIO",
                            id="btn-stop-scenario",
                            className="btn btn-danger",
                            style={"display": "none"},
                        ),
                    ], style={
                        "position":       "absolute",
                        "bottom":         "12px",
                        "right":          "12px",
                        "width":          "240px",
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
            html.Div([
                # ── Colonne gauche : vannes + état ──────────────────
                html.Div([

                    # Vannes
                    html.Div([
                        html.Div("Contrôle des Vannes", className="card-title"),

                        # V1 — admission HP (rôle principal)
                        html.Div([
                            html.Div("ADMISSION HP", style={
                                "fontSize": "9px", "color": "#334155",
                                "letterSpacing": "1.5px", "marginBottom": "6px",
                                "fontFamily": "Share Tech Mono",
                            }),
                            _slider_row("v1", "V1 — Admission HP",  100, "#f97316",
                                        "Contrôle 80% du débit HP — régulation principale"),
                        ]),

                        html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),

                        # V2/V3 — équilibrage mécanique
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

                        # MP/BP — extraction et condenseur
                        html.Div([
                            html.Div("EXTRACTION / CONDENSEUR", style={
                                "fontSize": "9px", "color": "#334155",
                                "letterSpacing": "1.5px", "marginBottom": "6px",
                                "fontFamily": "Share Tech Mono",
                            }),
                            _slider_row("mp", "Vanne MP — Extraction", 50, "#a78bfa",
                                        "Extraction vers barillet MP · P barillet monte si ouverture ↑"),
                            _slider_row("bp", "Vanne BP — Condenseur",  80, "#38bdf8",
                                        "Sortie BP vers condenseur · min 5% sécurité"),
                        ]),

                        html.Div([
                            html.Button("✔ Appliquer", id="btn-apply-valves",
                                        className="btn btn-success"),
                            html.Button("↺ Reset nominal", id="btn-reset",
                                        className="btn btn-danger",
                                        style={"marginLeft": "10px"}),
                        ], style={"marginTop": "14px"}),

                        html.Div(id="valve-feedback", style={
                            "marginTop": "10px",
                            "fontFamily": "Share Tech Mono",
                            "fontSize": "10.5px",
                            "color": "#64748b",
                            "minHeight": "20px",
                        }),
                    ], className="card"),

                    # État courant
                    # html.Div([
                    #     html.Div("État Système", className="card-title"),
                    #     html.Div(id="sim-state-panel"),
                    #     html.Button(
                    #         "🛑 ARRÊTER SCÉNARIO",
                    #         id="btn-stop-scenario",
                    #         className="btn btn-danger",
                    #         style={"display": "none"},
                    #     ),
                    # ], className="card", style={"marginTop": "14px"}),

                ], style={"flex": "1", "minWidth": "0"}),

                # ── Colonne droite : scénarios & historique ──────────────────────
                html.Div([
                    # Scénarios
                    html.Div([
                        html.Div([
                            html.Div("Scénarios de Perturbation", className="card-title"),
                            html.Div(id="scenarios-loading-header"), # Changement dynamique ici
                        ]),
                        html.Div(
                            id="scenarios-list-container",
                            style={"maxHeight": "480px", "overflowY": "auto",
                                   "paddingRight": "4px"},
                            children=[html.Div("Chargement des scénarios...", 
                                             style={"color": "#64748b", "fontFamily": "Share Tech Mono", "padding": "20px"})]
                        ),
                        html.Div(id="scenario-feedback", style={
                            "marginTop": "10px",
                            "fontFamily": "Share Tech Mono",
                            "fontSize": "10.5px",
                            "color": "#f97316",
                            "minHeight": "18px",
                        }),
                    ], className="card"),

                    # Historique
                    html.Div([
                        html.Div("Historique des Scénarios",
                                 className="card-title",
                                 style={"marginBottom": "10px"}),
                        html.Div(id="scenario-history-list",
                                 className="history-container",
                                 style={"maxHeight": "150px", "overflowY": "auto"}),
                    ], className="card", style={"marginTop": "14px"}),

                ], style={"flex": "1", "minWidth": "0", "display": "flex", "flexDirection": "column"}),

            ], style={"display": "flex", "gap": "16px", "alignItems": "flex-start"}),

        ], className="page-content"),
    ], className="main-content-wrap")