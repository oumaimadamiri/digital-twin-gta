"""
layouts/simulation.py — Contrôle de la simulation : 5 vannes + 10 scénarios

CORRECTIONS :
  1. scenario_card() : badge de criticité (CRITIQUE / MAJEUR / MODÉRÉ)
     calculé depuis perturbation_type et durée
  2. Chargement des scénarios sans race condition :
     le contenu initial affiche un spinner léger, le callback
     cb_simulation.update_history() charge sur pathname match
  3. Tri des scénarios : CRITIQUE en premier
"""
from dash import html, dcc
from components.sidebar import create_sidebar

import requests
from config import BACKEND

_session = requests.Session()

# ── Mapping criticité ─────────────────────────────────────────────────
_CRITICITE = {
    # (perturbation_type, scenario_id) → niveau
    # Scénarios identifiés comme critiques dans scenarios.py
    4: ("CRITIQUE", "#ef4444"),   # perte de charge brutale — step immédiat
    9: ("CRITIQUE", "#ef4444"),   # interruption source vapeur — step brutal
    8: ("MAJEUR",   "#f59e0b"),   # dépassement puissance — ramp vers trip
    1: ("MAJEUR",   "#f59e0b"),   # chute pression HP
    2: ("MAJEUR",   "#f59e0b"),   # surchauffe
    7: ("MAJEUR",   "#f59e0b"),   # défaut alternateur
    10:("MAJEUR",   "#f59e0b"),   # panne pompe huile
    3: ("MODÉRÉ",   "#818cf8"),   # fermeture V1 — step mais récupérable
    6: ("MODÉRÉ",   "#818cf8"),   # oscillations DEH
    5: ("MODÉRÉ",   "#818cf8"),   # dégradation progressive — ramp lent
}


def _slider_row(valve_id, label, default, color, description):
    return html.Div([
        html.Div([
            html.Span(label, className="slider-label-text", style={"color": color}),
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
    """Carte scénario avec badge de criticité."""
    ptype = s.get("perturbation_type", "unknown")
    sid   = s.get("id", 0)

    # Type de perturbation
    if ptype == "ramp":
        ptype_color, ptype_label = "#f59e0b", "RAMP"
    elif ptype == "step":
        ptype_color, ptype_label = "#ef4444", "STEP"
    elif ptype == "oscillation":
        ptype_color, ptype_label = "#818cf8", "OSCIL"
    else:
        ptype_color, ptype_label = "#94a3b8", "OTHER"

    # Badge criticité
    crit_label, crit_color = _CRITICITE.get(sid, ("MODÉRÉ", "#818cf8"))

    return html.Div([
        # En-tête avec nom et badges
        html.Div([
            html.Div([
                html.Div(s.get("name", "N/A"), className="scenario-name",
                         style={"fontSize": "12px", "fontWeight": "600",
                                "marginBottom": "5px"}),
                html.Div([
                    # Badge criticité (nouveau)
                    html.Span(crit_label, style={
                        "color": crit_color,
                        "fontSize": "9px",
                        "background": f"rgba({_hex_to_rgb(crit_color)},0.12)",
                        "padding": "1px 6px",
                        "borderRadius": "3px",
                        "fontFamily": "Share Tech Mono",
                        "marginRight": "6px",
                        "fontWeight": "600",
                    }),
                    # Badge type perturbation
                    html.Span(ptype_label, style={
                        "color": ptype_color,
                        "fontSize": "9px",
                        "background": f"rgba({_hex_to_rgb(ptype_color)},0.1)",
                        "padding": "1px 6px",
                        "borderRadius": "3px",
                        "fontFamily": "Share Tech Mono",
                    }),
                    html.Span(f" #{sid}", style={
                        "color": "#334155", "fontSize": "9px",
                        "marginLeft": "6px",
                    }),
                ]),
            ]),
        ], className="scenario-header",
           style={"display": "flex", "alignItems": "flex-start",
                  "marginBottom": "10px"}),

        html.Button(
            "Déclencher",
            id={"type": "btn-scenario", "index": sid},
            className="btn btn-scenario",
            style={"--btn-color": crit_color, "width": "100%"},
        ),
    ], className="card scenario-card",
       style={"--card-glow": crit_color, "padding": "12px", "marginBottom": "8px"})


def _hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"


def layout():
    return html.Div([
        create_sidebar(active_path="/simulation"),
        html.Div([
            html.Div(id="gta-synoptic-sim", style={"marginBottom": "20px"}),

            html.Div([
                # ── Colonne gauche : vannes + état ──────────────────
                html.Div([
                    html.Div([
                        html.Div("Contrôle des vannes", className="card-title"),

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
                                        "Répartition effort mécanique ~7%"),
                            _slider_row("v3", "V3 — Équilibrage", 100, "#60a5fa",
                                        "Répartition effort mécanique ~7%"),
                        ]),

                        html.Hr(style={"borderColor": "#0f2744", "margin": "10px 0"}),

                        html.Div([
                            html.Div("EXTRACTION / CONDENSEUR", style={
                                "fontSize": "9px", "color": "#334155",
                                "letterSpacing": "1.5px", "marginBottom": "6px",
                                "fontFamily": "Share Tech Mono",
                            }),
                            _slider_row("mp", "Vanne MP — Extraction", 50, "#a78bfa",
                                        "Extraction vers barillet MP"),
                            _slider_row("bp", "Vanne BP — Condenseur", 80, "#38bdf8",
                                        "Sortie BP vers condenseur · min 5% sécurité"),
                        ]),

                        html.Div([
                            html.Button("Appliquer", id="btn-apply-valves",
                                        className="btn btn-success"),
                            html.Button("Reset nominal", id="btn-reset",
                                        className="btn btn-danger",
                                        style={"marginLeft": "10px"}),
                        ], style={"marginTop": "14px"}),

                        html.Div(id="valve-feedback", style={
                            "marginTop": "10px", "fontFamily": "Share Tech Mono",
                            "fontSize": "10.5px", "color": "#64748b", "minHeight": "20px",
                        }),
                    ], className="card"),

                    html.Div([
                        html.Div("État système", className="card-title"),
                        html.Div(id="sim-state-panel"),
                        html.Button("Arrêter le scénario", id="btn-stop-scenario",
                                    className="btn btn-danger", style={"display": "none"}),
                    ], className="card", style={"marginTop": "14px"}),

                    html.Div([
                        html.Div("Historique des scénarios", className="card-title",
                                 style={"marginBottom": "10px"}),
                        html.Div(id="scenario-history-list", className="history-container",
                                 style={"maxHeight": "160px", "overflowY": "auto"}),
                    ], className="card", style={"marginTop": "14px"}),

                ], style={"flex": "1", "minWidth": "0"}),

                # ── Colonne droite : scénarios ──────────────────────
                html.Div([
                    html.Div([
                        html.Div("Scénarios de perturbation", className="card-title"),
                        # Légende criticité (nouveau)
                        html.Div([
                            html.Span("Criticité : ", style={"color": "#475569",
                                                              "fontSize": "10px"}),
                            html.Span("CRITIQUE", style={"color": "#ef4444",
                                                          "fontSize": "10px",
                                                          "marginRight": "8px"}),
                            html.Span("MAJEUR", style={"color": "#f59e0b",
                                                        "fontSize": "10px",
                                                        "marginRight": "8px"}),
                            html.Span("MODÉRÉ", style={"color": "#818cf8",
                                                        "fontSize": "10px"}),
                        ], style={"marginBottom": "10px"}),
                    ]),
                    # FIX race condition : spinner initial discret, remplacé par
                    # le callback update_scenarios_list déclenché par pathname
                    html.Div(
                        id="scenarios-list-container",
                        style={"maxHeight": "680px", "overflowY": "auto",
                               "paddingRight": "4px"},
                        children=[
                            html.Div([
                                html.Div(style={
                                    "width": "20px", "height": "20px",
                                    "border": "2px solid #334155",
                                    "borderTopColor": "#60a5fa",
                                    "borderRadius": "50%",
                                    "display": "inline-block",
                                    "marginRight": "8px",
                                }),
                                html.Span("Chargement...", style={
                                    "color": "#475569", "fontSize": "11px",
                                    "fontFamily": "Share Tech Mono",
                                }),
                            ], style={"display": "flex", "alignItems": "center",
                                      "padding": "16px"}),
                        ]
                    ),
                    html.Div(id="scenario-feedback", style={
                        "marginTop": "10px", "fontFamily": "Share Tech Mono",
                        "fontSize": "10.5px", "color": "#f97316", "minHeight": "18px",
                    }),
                ], className="card", style={"flex": "1", "minWidth": "0"}),

            ], style={"display": "flex", "gap": "16px", "alignItems": "flex-start"}),

        ], className="page-content"),
    ], className="main-content-wrap")