"""
layouts/analysis.py — Analyse & Historique
"""
from dash import html, dcc
from components.sidebar import create_sidebar, create_topbar
from config import BACKEND


def layout():
    return html.Div([
        create_sidebar(active_path="/analysis"),
        html.Div([
            create_topbar("Analyse & Historique", "Données Enregistrées"),

            html.Div([
                # ── FILTRES ──────────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Plage temporelle", className="filter-label"),
                        dcc.DatePickerRange(id="date-range",
                                            display_format="DD/MM/YYYY",
                                            className="custom-datepicker",
                                            style={"backgroundColor": "transparent"}),
                    ], style={"flex": "1"}),

                    html.Div([
                        html.Div("Paramètres à afficher", className="filter-label"),
                        dcc.Dropdown(id="param-selector",
                            options=[
                                {"label": "Pression HP (bar)",      "value": "pressure_hp"},
                                {"label": "Température HP (°C)",    "value": "temperature_hp"},
                                {"label": "Vitesse turbine (RPM)",  "value": "turbine_speed"},
                                {"label": "Puissance active (MW)",  "value": "active_power"},
                                {"label": "Facteur cosφ",           "value": "power_factor"},
                                {"label": "Rendement (%)",          "value": "efficiency"},
                                {"label": "Débit vapeur HP (T/h)",  "value": "steam_flow_hp"},
                            ],
                            value=["pressure_hp", "active_power", "turbine_speed"],
                            multi=True,
                            className="custom-dropdown",
                        ),
                    ], style={"flex": "2"}),

                    html.Div([
                        html.Div("Actions", className="filter-label"),
                        html.Div([
                            html.Button("🔄 Actualiser", id="btn-refresh-history",
                                        className="btn btn-primary", style={"fontSize": "11px"}),
                            html.A("⬇ CSV", id="btn-export-csv",
                                   href=f"{BACKEND}/data/export/csv",
                                   className="btn btn-warn",
                                   style={"marginLeft": "8px", "textDecoration": "none", "fontSize": "11px"}),
                        ]),
                    ], style={"flex": "0.7"}),

                ], className="card",
                   style={"display": "flex", "gap": "20px", "alignItems": "flex-start", "marginBottom": "16px"}),

                # ── GRAPHIQUE PRINCIPAL ───────────────────────
                html.Div([
                    html.Div("Évolution Temporelle Multi-Paramètres", className="card-title"),
                    dcc.Graph(id="history-chart", config={"displayModeBar": True},
                              style={"height": "300px"}),
                ], className="card", style={"marginBottom": "16px"}),

                # ── STATS + DISTRIBUTION ─────────────────────
                html.Div([
                    html.Div([
                        html.Div("Statistiques Descriptives", className="card-title"),
                        html.Div(id="stats-table"),
                    ], className="card", style={"flex": "3"}),

                    html.Div([
                        html.Div("Répartition des États", className="card-title"),
                        dcc.Graph(id="status-pie", config={"displayModeBar": False},
                                  style={"height": "220px"}),
                    ], className="card", style={"flex": "2"}),

                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),

                # ── TABLEAU DÉTAILLÉ ──────────────────────────
                html.Div([
                    html.Div("Journal de Données Détaillé", className="card-title"),
                    html.Div(id="history-data-table", style={"overflowX": "auto"}),
                ], className="card"),

            ], className="page-content"),

            dcc.Interval(id="interval-analysis", interval=10000, n_intervals=0),
        ], className="main-content"),
    ])