"""
layouts/ai_module.py — Vue Module IA

CORRECTIONS :
  1. Suppression de create_topbar → plus de double barre (économise 64px)
  2. Grid des 3 cartes IA : 1fr 1fr 1fr (colonnes égales) via style inline
     → chaque carte a le même espace, jauge AE lisible
  3. RUL : affichage couleur dynamique (vert/orange/rouge selon seuil)
  4. Alertes IA + Actions : layout flex conservé
"""
from dash import html, dcc
from components.sidebar import create_sidebar


def layout():
    return html.Div([
        create_sidebar(active_path="/ai"),
        html.Div([
            html.Div([
                # ── 3 cartes IA — grid égal 1fr 1fr 1fr ──────────────
                html.Div([

                    # Carte Autoencodeur
                    html.Div([
                        html.Div("Autoencodeur — détection d'anomalies",
                                 className="card-title"),
                        html.Div([
                            html.Div("Erreur de reconstruction", style={
                                "fontFamily": "var(--mono)", "fontSize": "11px",
                                "color": "var(--text3)", "marginBottom": "4px",
                            }),
                            html.Div(id="ae-error-value"),
                            html.Div(id="ae-status-label", style={"marginTop": "6px"}),
                        ], style={"marginBottom": "12px"}),
                        dcc.Loading(
                            dcc.Graph(id="ae-gauge", config={"displayModeBar": False}, style={"height": "190px"}),
                            type="circle", color="#00e676"
                        )
                    ], className="card"),

                    # Carte LSTM
                    html.Div([
                        html.Div("Prédiction LSTM — horizon court terme",
                                 className="card-title"),
                        html.Div([
                            html.Span("Précision modèle : ",
                                      style={"color": "var(--text3)", "fontSize": "11px"}),
                            html.Span(id="lstm-precision-value", style={
                                "fontFamily": "var(--mono)", "fontSize": "12px",
                                "color": "var(--green)", "marginLeft": "4px",
                            }),
                        ], style={"marginBottom": "6px"}),
                        dcc.Loading(
                            dcc.Graph(id="lstm-prediction-chart", config={"displayModeBar": False}, style={"height": "260px"}),
                            type="circle", color="#00e676"
                        )
                    ], className="card"),

                    # Carte RUL
                    html.Div([
                        html.Div("Remaining useful life (RUL)",
                                 className="card-title"),
                        html.Div([
                            html.Div("RUL estimé", style={
                                "fontFamily": "var(--mono)", "fontSize": "11px",
                                "color": "var(--text3)", "marginBottom": "4px",
                            }),
                            # Valeur colorée dynamiquement par cb_ai.py
                            html.Div(id="rul-value", style={
                                "fontFamily": "var(--mono)", "fontSize": "28px",
                                "fontWeight": "700", "color": "var(--green)",
                            }),
                            html.Div(id="rul-progress", style={"marginTop": "10px"}),
                        ]),
                    ], className="card"),

                # FIX : colonnes égales au lieu de 1.2fr 2fr 1.2fr
                ], style={
                    "display": "grid",
                    "gridTemplateColumns": "1fr 1fr 1fr",
                    "gap": "16px",
                    "marginBottom": "16px",
                }),

                # ── Alertes IA + actions ───────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Alertes IA récentes", className="card-title"),
                        dcc.Loading(
                            html.Div(id="ai-alerts-table"),
                            type="circle", color="#00e676"
                        ),
                    ], className="card", style={"flex": "3"}),

                    html.Div([
                        html.Div("Actions IA", className="card-title"),
                        html.Button(
                            "Lancer une analyse complète",
                            id="btn-run-ai",
                            className="btn btn-primary",
                            style={"width": "100%", "marginBottom": "10px"},
                        ),
                        html.Div(id="ai-run-status", style={
                            "fontFamily": "var(--mono)", "fontSize": "11px",
                            "color": "var(--text3)",
                        }),
                        html.Div(
                            "Rafraîchissement IA : 5s",
                            style={"color": "var(--text3)", "fontSize": "11px",
                                   "fontFamily": "var(--mono)", "marginTop": "16px"},
                        ),
                    ], className="card", style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),

                dcc.Interval(id="interval-ai", interval=5000, n_intervals=0),

            ], className="page-content"),
        ], className="main-content"),
    ], className="main-content-wrap")