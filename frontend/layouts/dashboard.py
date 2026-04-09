"""
layouts/dashboard.py — Vue Dashboard temps réel SCADA

Refactoring :
  - Les jauges ont été déplacées sur la page Analyse (KPIs contextuels sur période).
  - Le dashboard se concentre sur : synoptique P&ID + graphique RT + alertes.
  - Vue 100% opérationnelle : l'opérateur voit l'état global sans scroller.
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.gta_synoptic import create_gta_synoptic_static
from callbacks.cb_dashboard import make_empty_rt_figure


def layout():
    return html.Div([
        create_sidebar(active_path="/"),
        html.Div([
            html.Div([

                # ── Synoptique P&ID ────────────────────────────────────────
                html.Div(
                    className="synoptic-bleed",
                    style={"position": "relative", "marginBottom": "20px", "minHeight": "520px"},
                    children=[
                        html.Div(
                            id="gta-synoptic",
                            children=[create_gta_synoptic_static()],
                            style={"minHeight": "520px"},
                        ),
                        # Panneau état superposé en bas à droite
                        html.Div(
                            id="dash-state-panel",
                            style={
                                "position":       "absolute",
                                "bottom":         "25px",
                                "right":          "12px",
                                "width":          "220px",
                                "background":     "rgba(10,16,26,0.92)",
                                "border":         "1px solid #1e3a5f",
                                "borderRadius":   "8px",
                                "padding":        "12px",
                                "zIndex":         "10",
                                "backdropFilter": "blur(4px)",
                            },
                        ),
                    ],
                ),

                # ── Graphique tendances temps réel ─────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Tendances temps réel", className="card-title"),
                        html.Div([
                            html.Span("6 paramètres clés — fenêtre glissante 2m30s",
                                      style={"color": "#334155", "fontSize": "10px",
                                             "fontFamily": "Share Tech Mono"}),
                            html.Div(id="topbar-time", style={
                                "color": "#60a5fa", "fontSize": "11px",
                                "fontFamily": "Share Tech Mono",
                            }),
                        ], style={"display": "flex", "justifyContent": "space-between",
                                  "alignItems": "center", "marginBottom": "8px"}),
                    ]),
                    dcc.Graph(
                        id="realtime-chart",
                        config={"displayModeBar": False},
                        style={"height": "300px"},
                        figure=make_empty_rt_figure(),
                    ),
                ], className="card", style={"marginBottom": "20px"}),

                # ── Alertes actives ────────────────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Alertes actives", className="card-title"),
                        html.Div(id="topbar-status-pill",
                                 style={"fontSize": "11px", "fontFamily": "Share Tech Mono",
                                        "color": "#10b981", "fontWeight": "700"}),
                    ], style={"display": "flex", "justifyContent": "space-between",
                               "alignItems": "center", "marginBottom": "12px"}),
                    html.Div(id="alerts-panel"),
                ], className="card"),

            ], className="page-content"),
        ], className="main-content"),
    ], className="main-content-wrap")