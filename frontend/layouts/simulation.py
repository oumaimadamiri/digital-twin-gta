"""
layouts/simulation.py — Contrôle de la simulation : vannes + scénarios
"""
from dash import html, dcc
from components.sidebar import create_sidebar, create_topbar

SCENARIOS = [
    {"id": 1, "name": "Chute de pression HP",          "icon": "📉", "color": "#00b4ff"},
    {"id": 2, "name": "Surchauffe vapeur HP",           "icon": "🔥", "color": "#ff7043"},
    {"id": 3, "name": "Fermeture partielle V1",         "icon": "🔧", "color": "#aa80ff"},
    {"id": 4, "name": "Perte de charge brutale",        "icon": "⚡", "color": "#ffd740"},
    {"id": 5, "name": "Dégradation progressive",        "icon": "📊", "color": "#00e5ff"},
    {"id": 6, "name": "Oscillations de pression",       "icon": "〜", "color": "#00e676"},
    {"id": 7, "name": "Défaut alternateur (cosφ)",      "icon": "⚠", "color": "#ff3d57"},
]

def scenario_card(s):
    return html.Div([
        html.Div([
            html.Span(s["icon"], className="scenario-icon"),
            html.Div([
                html.Div(s["name"], className="scenario-name"),
                html.Div(f"Scénario #{s['id']}", className="scenario-id"),
            ]),
        ], className="scenario-header"),
        html.Button("▶ DÉCLENCHER", id=f"btn-scenario-{s['id']}",
                    className="btn btn-scenario",
                    style={"--btn-color": s["color"]}),
    ], className="card scenario-card", style={"--card-glow": s["color"]})


def layout():
    return html.Div([
        create_sidebar(active_path="/simulation"),
        html.Div([
            create_topbar("Simulation", "Contrôle Interactif"),

            # Schéma Synoptique de Simulation
            html.Div(id="gta-synoptic-sim", style={"marginBottom": "24px"}),

            html.Div([
                html.Div([
                    # ── VANNES ───────────────────────────────
                    html.Div([
                        html.Div("Contrôle des Vannes", className="card-title"),

                        *[html.Div([
                            html.Div([
                                html.Span(f"Vanne {v}", className="slider-label-text"),
                                html.Span(id=f"val-v{i+1}", className="slider-val-num"),
                                html.Span("%", className="slider-val-unit"),
                            ], className="slider-label-row"),
                            dcc.Slider(id=f"slider-v{i+1}", min=0, max=100, step=1, value=100,
                                       marks={0: "0%", 25: "25%", 50: "50%", 75: "75%", 100: "100%"},
                                       className="custom-slider",
                                       tooltip={"placement": "bottom", "always_visible": False}),
                        ], className="slider-container") for i, v in enumerate(["V1 — Admission HP", "V2 — Extraction MP", "V3 — Sortie BP"])],

                        html.Div([
                            html.Button("✔ Appliquer", id="btn-apply-valves", className="btn btn-success"),
                            html.Button("↺ Reset nominal", id="btn-reset", className="btn btn-danger",
                                        style={"marginLeft": "10px"}),
                        ], style={"marginTop": "16px"}),

                        html.Div(id="valve-feedback", style={"marginTop": "12px", "fontFamily": "Share Tech Mono",
                                                              "fontSize": "11px", "color": "#6a96bb"}),
                    ], className="card"),

                    # ── ÉTAT COURANT ─────────────────────────
                    html.Div([
                        html.Div("État Système", className="card-title"),
                        html.Div(id="sim-state-panel"),
                        html.Button("🛑 ARRÊTER SCÉNARIO", id="btn-stop-scenario",
                                    className="btn btn-danger", style={"marginTop": "16px", "width": "100%", "display": "none"})
                    ], className="card", style={"marginTop": "16px"}),

                    # ── HISTORIQUE ───────────────────────────
                    html.Div([
                        html.Div("Historique des Scénarios", className="card-title", style={"marginTop": "20px"}),
                        html.Div(id="scenario-history-list", className="history-container")
                    ], className="card", style={"marginTop": "16px"}),

                ], style={"flex": "1"}),

                # ── SCÉNARIOS ────────────────────────────────
                html.Div([
                    html.Div("Scénarios de Perturbation", className="card-title"),
                    html.Div([scenario_card(s) for s in SCENARIOS],
                             style={"display": "flex", "flexDirection": "column", "gap": "10px"}),
                    html.Div(id="scenario-feedback", style={"marginTop": "12px", "fontFamily": "Share Tech Mono",
                                                               "fontSize": "11px", "color": "#ff7043"}),
                ], className="card", style={"flex": "1"}),

            ], style={"display": "flex", "gap": "16px"}),

        ], className="page-content"),
    ], className="main-content"),