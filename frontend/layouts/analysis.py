"""
layouts/analysis.py — Analyse & Historique

CORRECTIONS :
  1. DatePickerRange remplacé par 2 dcc.Input(type="date")
     → plus de pop-up blanc incohérent avec le thème sombre
  2. Boutons de filtres rapides : 1h · 6h · 24h · 7j · Tout
     → l'opérateur n'a pas besoin de saisir les dates manuellement
  3. Graphique principal : hauteur portée à 320px (était 300px)
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from config import BACKEND
from datetime import datetime, date


def layout():
    today = date.today().isoformat()

    return html.Div([
        create_sidebar(active_path="/analysis"),
        html.Div([
            html.Div([

                # ── FILTRES ──────────────────────────────────────────
                html.Div([

                    # Filtres rapides (nouveau)
                    html.Div([
                        html.Div("Période rapide", className="filter-label"),
                        html.Div([
                            html.Button("1h",   id="qf-1h",   className="btn btn-outline",
                                        style={"fontSize": "11px", "padding": "6px 12px"}),
                            html.Button("6h",   id="qf-6h",   className="btn btn-outline",
                                        style={"fontSize": "11px", "padding": "6px 12px"}),
                            html.Button("24h",  id="qf-24h",  className="btn btn-outline",
                                        style={"fontSize": "11px", "padding": "6px 12px"}),
                            html.Button("7j",   id="qf-7j",   className="btn btn-outline",
                                        style={"fontSize": "11px", "padding": "6px 12px"}),
                            html.Button("Tout", id="qf-all",  className="btn btn-outline",
                                        style={"fontSize": "11px", "padding": "6px 12px"}),
                        ], style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
                    ], style={"flex": "0 0 auto"}),

                    # Plage manuelle — FIX : dcc.Input(type="date") au lieu de DatePickerRange
                    html.Div([
                        html.Div("Plage personnalisée", className="filter-label"),
                        html.Div([
                            dcc.Input(
                                id="date-start",
                                type="date",
                                value=None,
                                className="custom-input",
                                style={"width": "145px"},
                            ),
                            html.Span("→", style={
                                "color": "var(--text3)", "fontSize": "12px",
                                "alignSelf": "center",
                            }),
                            dcc.Input(
                                id="date-end",
                                type="date",
                                value=today,
                                className="custom-input",
                                style={"width": "145px"},
                            ),
                        ], style={"display": "flex", "gap": "8px", "alignItems": "center"}),
                    ], style={"flex": "1"}),

                    # Paramètres
                    html.Div([
                        html.Div("Paramètres", className="filter-label"),
                        dcc.Dropdown(id="param-selector",
                            options=[
                                {"label": "Pression HP (bar)",     "value": "pressure_hp"},
                                {"label": "Température HP (°C)",   "value": "temperature_hp"},
                                {"label": "Vitesse turbine (RPM)", "value": "turbine_speed"},
                                {"label": "Puissance active (MW)", "value": "active_power"},
                                {"label": "Facteur cosφ",          "value": "power_factor"},
                                {"label": "Rendement (%)",         "value": "efficiency"},
                                {"label": "Débit vapeur HP (T/h)", "value": "steam_flow_hp"},
                            ],
                            value=["pressure_hp", "active_power", "turbine_speed"],
                            multi=True,
                            className="custom-dropdown",
                        ),
                    ], style={"flex": "2"}),

                    # Actions
                    html.Div([
                        html.Div("Actions", className="filter-label"),
                        html.Div([
                            html.Button("Actualiser", id="btn-refresh-history",
                                        className="btn btn-primary",
                                        style={"fontSize": "11px"}),
                            html.A("CSV", id="btn-export-csv",
                                   href=f"{BACKEND}/data/export/csv",
                                   className="btn btn-warn",
                                   style={"marginLeft": "8px", "textDecoration": "none",
                                          "fontSize": "11px"}),
                        ]),
                    ], style={"flex": "0 0 auto"}),

                ], className="card",
                   style={"display": "flex", "gap": "16px", "alignItems": "flex-start",
                          "flexWrap": "wrap", "marginBottom": "16px"}),

                # ── GRAPHIQUE PRINCIPAL — 320px (était 300px) ─────────
                html.Div([
                    html.Div("Évolution temporelle multi-paramètres",
                             className="card-title"),
                    dcc.Graph(id="history-chart", config={"displayModeBar": True},
                               style={"height": "320px"}),
                ], className="card", style={"marginBottom": "16px"}),

                # ── STATS + DISTRIBUTION ─────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Statistiques descriptives", className="card-title"),
                        html.Div(id="stats-table"),
                    ], className="card", style={"flex": "3"}),

                    html.Div([
                        html.Div("Répartition des états", className="card-title"),
                        dcc.Graph(id="status-pie", config={"displayModeBar": False},
                                  style={"height": "220px"}),
                    ], className="card", style={"flex": "2"}),

                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),

                # ── TABLEAU DÉTAILLÉ ──────────────────────────────────
                html.Div([
                    html.Div("Journal de données détaillé", className="card-title"),
                    html.Div(id="history-data-table", style={"overflowX": "auto"}),
                ], className="card"),

            ], className="page-content"),

            dcc.Interval(id="interval-analysis", interval=10000, n_intervals=0),
        ], className="main-content"),
    ], className="main-content-wrap")