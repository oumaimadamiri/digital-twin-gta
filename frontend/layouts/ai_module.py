"""
layouts/ai_module.py — Vue Module IA
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.gauges import create_empty_fig

def layout():
    return html.Div([
        create_sidebar(active_path="/ai"),
        html.Div([
            html.Div([

                # ── Bandeau "Dernier réentraînement" ────────────────────
                html.Div([
                    html.Div("Analyse Prédictive IA", className="card-title",
                             style={"marginBottom": "0"}),
                    html.Div(id="ai-last-training-badge",
                             className="refresh-badge",
                             style={"marginLeft": "auto"}),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "4px"}),

                # ── 3 cartes modèles ─────────────────────────────────────
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div("Modèle Autoencodeur", className="mc-name"),
                            html.Div("ACTIF", id="mc-ae-badge", className="mc-badge"),
                        ], className="mc-header"),
                        html.Div(id="mc-ae-value", className="mc-value"),
                        html.Div(id="mc-ae-sub", className="mc-sub"),
                        html.Div("🧠", className="mc-icon"),
                    ], className="model-card mc-ae"),
                    html.Div([
                        html.Div([
                            html.Div("Modèle LSTM", className="mc-name"),
                            html.Div("ACTIF", className="mc-badge"),
                        ], className="mc-header"),
                        html.Div(id="mc-lstm-value", className="mc-value"),
                        html.Div(id="mc-lstm-sub", className="mc-sub"),
                        html.Div("📉", className="mc-icon"),
                    ], className="model-card mc-lstm"),

                    html.Div([
                        html.Div([
                            html.Div("Modèle RUL (dégradation)", className="mc-name"),
                            html.Div("ACTIF", className="mc-badge"),
                        ], className="mc-header"),
                        html.Div(id="mc-xgb-value", className="mc-value"),
                        html.Div(id="mc-xgb-sub", className="mc-sub"),
                        html.Div("⏱️", className="mc-icon"),
                    ], className="model-card mc-xgb"),
                ], className="model-cards", style={"marginBottom": "16px"}),
                # ── Ligne du milieu : Anomalies + Prédiction ─────────────
                html.Div([

                    # Panneau anomalies
                    html.Div([
                        html.Div([
                            html.Div("🔍 Détection d'anomalies", className="card-title",
                                     style={"marginBottom": "0"}),
                            html.Div("Refresh : 5s", className="refresh-badge"),
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),

                        dcc.Graph(id="ae-gauge",
                                  figure=create_empty_fig(180, "Initialisation AE..."),
                                  config={"displayModeBar": False}, style={"height": "180px"}),
                        html.Div(id="ae-status-label", style={"textAlign": "center", "marginBottom": "10px"}),

                        html.Div("Timeline des 20 derniers points (historique réel)",
                                 className="timeline-label"),
                        html.Div(id="ae-timeline", className="timeline"),
                        html.Div([
                            html.Span(id="ae-timeline-start", className="tl-axis-label"),
                            html.Span("Maintenant", className="tl-axis-label"),
                        ], className="timeline-axis"),
                    ], className="anomaly-panel"),
                    # Panneau prédiction LSTM + RUL
                    html.Div([
                        html.Div("📊 Prédiction de performances (LSTM)", className="card-title"),
                        dcc.Graph(id="lstm-prediction-chart",
                                  figure=create_empty_fig(180, "Calcul prédictions..."),
                                  config={"displayModeBar": False}, style={"height": "180px"}),

                        html.Div([
                            html.Div([
                                html.Div("📅 RUL (Remaining Useful Life)", className="rul-title"),
                                html.Div(id="rul-value", style={
                                    "fontFamily": "var(--mono)", "fontSize": "16px", "fontWeight": "700",
                                    "color": "var(--green)",
                                }),
                            ], className="rul-header"),
                            html.Div(id="rul-progress"),
                        ], className="rul-card"),
                    ], className="pred-panel"),

                ], className="middle-row", style={"marginBottom": "16px"}),
                # ── Alertes IA + actions ───────────────────────────────
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div("📋 Alertes IA récentes", className="card-title",
                                     style={"marginBottom": "0"}),
                            html.A("⬇ Exporter CSV", id="ai-alerts-export-link", href="#",
                                   style={"fontSize": "11px", "color": "var(--blue)",
                                          "textDecoration": "underline", "marginLeft": "auto"}),
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
                        html.Div(id="ai-alerts-table")
                    ], className="card", style={"flex": "3"}),

                    html.Div([
                        html.Div("Actions IA", className="card-title"),
                        html.P(
                            "Force immédiatement une nouvelle analyse (détection d'anomalie, "
                            "prédiction LSTM, RUL) sans attendre le rafraîchissement automatique "
                            "toutes les 5 secondes.",
                            style={
                                "fontSize": "11px", "color": "var(--text3)",
                                "marginTop": "0", "marginBottom": "10px", "lineHeight": "1.4",
                            },
                        ),
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
                    ], className="card", style={"flex": "1"}),
                ], style={"display": "flex", "gap": "16px"}),
                dcc.Interval(id="interval-ai", interval=5000, n_intervals=0),

            ], className="page-content"),
        ], className="main-content"),
    ], className="main-content-wrap")