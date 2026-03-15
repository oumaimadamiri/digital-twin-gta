"""
layouts/simulation.py — Contrôle de la simulation : 5 vannes + 10 scénarios
"""
from dash import html, dcc
from components.sidebar import create_sidebar, create_topbar

# ── Métadonnées des 10 scénarios ──────────────────────────────────────
SCENARIOS = [
    {"id": 1,  "name": "Chute de pression HP",             "icon": "📉", "color": "#00b4ff", "type": "Rampe"},
    {"id": 2,  "name": "Surchauffe vapeur HP",             "icon": "🌡", "color": "#ff7043", "type": "Rampe"},
    {"id": 3,  "name": "Fermeture partielle V1",           "icon": "🔧", "color": "#aa80ff", "type": "Échelon"},
    {"id": 4,  "name": "Perte de charge brutale",          "icon": "⚡", "color": "#ffd740", "type": "Échelon"},
    {"id": 5,  "name": "Dégradation progressive rendement","icon": "📊", "color": "#00e5ff", "type": "Rampe"},
    {"id": 6,  "name": "Oscillations pression (DEH)",      "icon": "〜", "color": "#00e676", "type": "Oscill."},
    {"id": 7,  "name": "Défaut alternateur (cos φ)",       "icon": "⚠",  "color": "#ff3d57", "type": "Échelon"},
    {"id": 8,  "name": "Dépassement 24MW → surpression BP","icon": "🔺", "color": "#f97316", "type": "Rampe"},
    {"id": 9,  "name": "Interruption source vapeur",       "icon": "🚫", "color": "#ef4444", "type": "Échelon"},
    {"id": 10, "name": "Panne pompe refroidissement huile","icon": "💧", "color": "#38bdf8", "type": "Rampe"},
]


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
    return html.Div([
        html.Div([
            html.Span(s["icon"], className="scenario-icon",
                      style={"fontSize": "18px", "marginRight": "8px"}),
            html.Div([
                html.Div(s["name"], className="scenario-name",
                         style={"fontSize": "12px", "fontWeight": "600"}),
                html.Div([
                    html.Span(f"#{s['id']}", style={"color": "#334155",
                                                      "marginRight": "8px",
                                                      "fontSize": "10px"}),
                    html.Span(s["type"],
                              style={"color": s["color"], "fontSize": "10px",
                                     "background": f"rgba({_hex_to_rgb(s['color'])},0.1)",
                                     "padding": "1px 6px", "borderRadius": "3px",
                                     "fontFamily": "Share Tech Mono"}),
                ]),
            ]),
        ], className="scenario-header",
           style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
        html.Button(
            "▶ DÉCLENCHER",
            id=f"btn-scenario-{s['id']}",
            className="btn btn-scenario",
            style={"--btn-color": s["color"], "width": "100%"},
        ),
    ], className="card scenario-card",
       style={"--card-glow": s["color"], "padding": "12px", "marginBottom": "8px"})


def _hex_to_rgb(hex_color):
    """Convertit #rrggbb en 'r,g,b' pour rgba()."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"


def layout():
    return html.Div([
        create_sidebar(active_path="/simulation"),
        html.Div([
            create_topbar("Simulation", "Contrôle Interactif"),

            # Synoptique simulation
            html.Div(id="gta-synoptic-sim", style={"marginBottom": "20px"}),

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
                    html.Div([
                        html.Div("État Système", className="card-title"),
                        html.Div(id="sim-state-panel"),
                        html.Button(
                            "🛑 ARRÊTER SCÉNARIO",
                            id="btn-stop-scenario",
                            className="btn btn-danger",
                            style={"display": "none"},
                        ),
                    ], className="card", style={"marginTop": "14px"}),

                    # Historique
                    html.Div([
                        html.Div("Historique des Scénarios",
                                 className="card-title",
                                 style={"marginBottom": "10px"}),
                        html.Div(id="scenario-history-list",
                                 className="history-container",
                                 style={"maxHeight": "160px", "overflowY": "auto"}),
                    ], className="card", style={"marginTop": "14px"}),

                ], style={"flex": "1", "minWidth": "0"}),

                # ── Colonne droite : scénarios ──────────────────────
                html.Div([
                    html.Div([
                        html.Div("Scénarios de Perturbation", className="card-title"),
                        html.Div([
                            html.Span(str(len(SCENARIOS)),
                                      style={"color": "#818cf8", "fontWeight": "700"}),
                            html.Span(" scénarios disponibles",
                                      style={"color": "#334155", "fontSize": "11px",
                                             "fontFamily": "Share Tech Mono"}),
                        ], style={"marginBottom": "12px"}),
                    ]),
                    html.Div(
                        [scenario_card(s) for s in SCENARIOS],
                        style={"maxHeight": "680px", "overflowY": "auto",
                               "paddingRight": "4px"},
                    ),
                    html.Div(id="scenario-feedback", style={
                        "marginTop": "10px",
                        "fontFamily": "Share Tech Mono",
                        "fontSize": "10.5px",
                        "color": "#f97316",
                        "minHeight": "18px",
                    }),
                ], className="card", style={"flex": "1", "minWidth": "0"}),

            ], style={"display": "flex", "gap": "16px", "alignItems": "flex-start"}),

        ], className="page-content"),
    ], className="main-content-wrap")