"""
layouts/ai_module.py — Vue Module IA
"""
from dash import html, dcc
from components.sidebar import create_sidebar, create_topbar


def layout():
    return html.Div([
        create_sidebar(active_path="/ai"),
        html.Div([
            create_topbar("Module IA", "Détection d'Anomalies & RUL"),

            html.Div([
                # ── Carte Autoencodeur ─────────────────────────────
                html.Div([
                    html.Div("Autoencodeur — Détection d'Anomalies", className="card-title"),
                    html.Div([
                        html.Div("Erreur de reconstruction", style={
                            "fontFamily": "var(--mono)",
                            "fontSize": "11px",
                            "color": "var(--text3)",
                            "marginBottom": "4px",
                        }),
                        html.Div(id="ae-error-value"),
                        html.Div(id="ae-status-label", style={
                            "marginTop": "6px",
                        }),
                    ], style={"marginBottom": "12px"}),
                    dcc.Graph(id="ae-gauge", config={"displayModeBar": False},
                              style={"height": "190px"}),
                ], className="card", style={"flex": "1"}),

                # ── Carte LSTM ────────────────────────────────────
                html.Div([
                    html.Div("Prédiction LSTM — Horizon Court Terme", className="card-title"),
                    html.Div([
                        html.Span("Précision attendue : ",
                                  style={"color": "var(--text3)", "fontSize": "11px"}),
                        html.Span(id="lstm-precision-value",
                                  style={"fontFamily": "var(--mono)",
                                         "fontSize": "12px", "color": "var(--green)",
                                         "marginLeft": "4px"}),
                    ], style={"marginBottom": "6px"}),
                    dcc.Graph(id="lstm-prediction-chart",
                              config={"displayModeBar": False},
                              style={"height": "260px"}),
                ], className="card", style={"flex": "2"}),

                # ── Carte RUL ─────────────────────────────────────
                html.Div([
                    html.Div("Remaining Useful Life (RUL)", className="card-title"),
                    html.Div([
                        html.Div("RUL estimé", style={
                            "fontFamily": "var(--mono)",
                            "fontSize": "11px",
                            "color": "var(--text3)",
                            "marginBottom": "4px",
                        }),
                        html.Div(id="rul-value", style={
                            "fontFamily": "var(--mono)",
                            "fontSize": "28px",
                            "fontWeight": "700",
                            "color": "var(--green)",
                        }),
                        html.Div(id="rul-progress", style={"marginTop": "10px"}),
                    ]),
                ], className="card", style={"flex": "1"}),

            ], style={"display": "grid", "gridTemplateColumns": "1.2fr 2fr 1.2fr", "gap": "16px",
                      "marginBottom": "16px"}),

            # ── Alertes IA + actions ─────────────────────────────
            html.Div([
                html.Div([
                    html.Div("Alertes IA Récentes", className="card-title"),
                    html.Div(id="ai-alerts-table"),
                ], className="card", style={"flex": "3"}),

                html.Div([
                    html.Div("Actions IA", className="card-title"),
                    html.Button("▶ Lancer une analyse complète", id="btn-run-ai",
                                className="btn btn-primary",
                                style={"width": "100%", "marginBottom": "10px"}),
                    html.Div(id="ai-run-status", style={
                        "fontFamily": "var(--mono)",
                        "fontSize": "11px",
                        "color": "var(--text3)",
                    }),
                    html.Div([
                        html.Div("Fréquence de rafraîchissement IA : 5s",
                                 style={"color": "var(--text3)", "fontSize": "11px",
                                        "fontFamily": "var(--mono)",
                                        "marginTop": "16px"}),
                    ]),
                ], className="card", style={"flex": "1"}),
            ], style={"display": "flex", "gap": "16px"}),

            dcc.Interval(id="interval-ai", interval=5000, n_intervals=0),

        ], className="page-content"),
    ], className="main-content")

