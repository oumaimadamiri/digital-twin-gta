"""
layouts/dashboard.py — Vue Dashboard temps réel SCADA

MODIFICATIONS (refactor graphe) :
  - Suppression du graphe "Tendances temps réel" 300px (redondant avec Analyse)
  - Ajout d'un mini-sparkline 140px affichant UN seul paramètre à la fois
  - Sélection du paramètre via boutons OU clic sur un tag du synoptique SVG
  - Le paramètre actif est mémorisé dans store-spark-param (persistant entre pushes)
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.gta_synoptic import create_gta_synoptic_static
from callbacks.cb_dashboard import make_empty_spark_figure


def layout():
    return html.Div([
        dcc.Store(id="store-spark-group-idx", data=0),
        create_sidebar(active_path="/"),
        html.Div([
            html.Div([

                # ── Synoptique P&ID (table État Système intégrée dans le SVG) ──
                html.Div(
                    className="synoptic-bleed",
                    style={"marginBottom": "20px"},
                    children=[
                        html.Div(
                            id="gta-synoptic",
                            children=[create_gta_synoptic_static()],
                        ),
                    ],
                ),

                # ── Popup graphe paramètre (déclenché par clic sur tag SVG) ──
                html.Div(
                    id="spark-modal",
                    style={"display": "none"},
                    children=[
                        # Backdrop cliquable pour fermer
                        html.Div(
                            id="spark-modal-backdrop",
                            n_clicks=0,
                            style={
                                "position":   "fixed",
                                "inset":      "0",
                                "background": "rgba(3, 8, 15, 0.65)",
                                "backdropFilter": "blur(3px)",
                                "zIndex":     "999",
                                "cursor":     "pointer",
                            },
                        ),
                        # Fenêtre centrée
                        html.Div(
                            className="card spark-modal-card",
                            style={
                                "position":   "fixed",
                                "top":        "50%",
                                "left":       "50%",
                                "transform":  "translate(-50%, -50%)",
                                "width":      "min(640px, 94vw)",
                                "zIndex":     "1000",
                                "boxShadow":  "0 12px 40px rgba(0,0,0,0.6)",
                                "border":     "1px solid #1e3a5f",
                            },
                            children=[
                                # Header : titre + close
                                html.Div([
                                    html.Div([
                                        html.Span("●", id="spark-modal-dot", style={
                                            "fontSize": "11px", "marginRight": "8px",
                                        }),
                                        html.Span(id="spark-modal-title", style={
                                            "fontFamily": "Share Tech Mono",
                                            "fontSize":   "13px",
                                            "color":      "#e2e8f0",
                                            "letterSpacing": "1px",
                                            "fontWeight": "700",
                                        }),
                                    ], style={"display": "flex", "alignItems": "center"}),
                                    html.Button(
                                        "×",
                                        id="spark-modal-close",
                                        n_clicks=0,
                                        style={
                                            "background": "transparent",
                                            "border":     "none",
                                            "color":      "#94a3b8",
                                            "fontSize":   "22px",
                                            "fontWeight": "700",
                                            "cursor":     "pointer",
                                            "lineHeight": "1",
                                            "padding":    "0 6px",
                                        },
                                    ),
                                ], style={
                                    "display":        "flex",
                                    "justifyContent": "space-between",
                                    "alignItems":     "center",
                                    "marginBottom":   "10px",
                                    "borderBottom":   "1px solid #1e3a5f",
                                    "paddingBottom":  "8px",
                                }),

                                # Barre d'onglets (groupe uniquement)
                                html.Div(
                                    id="spark-nav-bar",
                                    style={"display": "none"},
                                    children=[],
                                ),

                                # Graphe
                                dcc.Graph(
                                    id="spark-chart",
                                    config={"displayModeBar": False},
                                    style={"height": "280px"},
                                    figure=make_empty_spark_figure("active_power"),
                                ),

                                # Label bas
                                html.Div(id="spark-param-label", style={
                                    "fontFamily": "Share Tech Mono",
                                    "fontSize":   "10px",
                                    "color":      "#64748b",
                                    "textAlign":  "right",
                                    "marginTop":  "4px",
                                }),
                            ],
                        ),
                    ],
                ),

                # ── Alertes actives ────────────────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Alertes actives", className="card-title"),
                        ], style={"display": "flex", "justifyContent": "space-between",
                               "alignItems": "center", "marginBottom": "12px"}),
                    html.Div(id="alerts-panel"),
                ], className="card"),

            ], className="page-content"),
        ], className="main-content"),
], className="main-content-wrap")