"""
layouts/analysis.py — Analyse & Historique

Ajouts :
  1. Bande KPI dynamique en haut — métriques calculées sur la période filtrée
     (puissance moy/max, rendement moy vs nominal, alertes, % temps dégradé).
  2. Section jauges temps réel (déplacées depuis Dashboard) — toujours live.
  3. DatePickerRange remplacé par 2 dcc.Input(type="date").
  4. Boutons de filtres rapides : 1h · 6h · 24h · 7j · Tout.
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.gauges import gauge_card, make_gauge, create_empty_fig, GAUGE_CONFIGS
from config import BACKEND
from datetime import date


# ── Groupes de jauges (identiques à l'ancien dashboard) ──────────────────────
_GAUGES_FAST = ["pressure_hp", "temperature_hp", "active_power",
                "turbine_speed", "efficiency"]

_GAUGES_SLOW_ELEC = ["reactive_power", "apparent_power", "power_factor",
                     "current_a", "voltage"]

_GAUGES_SLOW_BP   = ["steam_flow_hp", "pressure_bp_in", "pressure_bp_barillet",
                     "steam_flow_condenser"]


def _gauge_section(title, gauge_keys, color):
    return html.Div([
        html.Div([
            html.Span(style={
                "display": "inline-block", "width": "8px", "height": "8px",
                "borderRadius": "50%", "background": color,
                "marginRight": "8px", "verticalAlign": "middle",
            }),
            html.Span(title, style={
                "color": "#64748b", "fontSize": "10px",
                "fontFamily": "Share Tech Mono", "letterSpacing": "1.5px",
                "textTransform": "uppercase",
            }),
        ], style={"marginBottom": "8px", "paddingLeft": "4px"}),
        html.Div(
            [gauge_card(f"gauge-{k}", make_gauge(
                 GAUGE_CONFIGS[k]["min"] + (GAUGE_CONFIGS[k]["max"] - GAUGE_CONFIGS[k]["min"]) * 0.5,
                 GAUGE_CONFIGS[k]
             )) for k in gauge_keys],
            style={
                "display": "grid",
                "gridTemplateColumns": f"repeat({len(gauge_keys)}, 1fr)",
                "gap": "8px",
            },
        ),
    ], style={"marginBottom": "16px"})


def _kpi_badge(badge_id, label, value_id, unit, color, sub_id=None, sub_label=""):
    return html.Div([
        html.Div(label, className="kpi-label"),
        html.Div([
            html.Span(id=value_id, className="kpi-val-num",
                      style={"color": color, "fontFamily": "Share Tech Mono",
                             "fontSize": "22px", "fontWeight": "700"}),
            html.Span(f" {unit}", className="kpi-unit"),
        ], className="kpi-val"),
        html.Div(id=sub_id, className="kpi-sub",
                 style={"color": "#64748b", "fontSize": "10px",
                        "fontFamily": "Share Tech Mono", "marginTop": "4px"})
        if sub_id else html.Div(sub_label, className="kpi-sub",
                                style={"color": "#64748b", "fontSize": "10px",
                                       "fontFamily": "Share Tech Mono", "marginTop": "4px"}),
    ], id=badge_id, className="kpi-badge")


def layout():
    today = date.today().isoformat()

    return html.Div([
        create_sidebar(active_path="/analysis"),
        html.Div([
            html.Div([

                # ══════════════════════════════════════════════════════════
                # BANDE KPI — résumé sur la période sélectionnée
                # ══════════════════════════════════════════════════════════
                html.Div([
                    html.Div("Indicateurs sur la période sélectionnée",
                             className="card-title",
                             style={"marginBottom": "12px"}),
                    html.Div([
                        _kpi_badge("kpi-power-avg",  "Puissance moyenne",
                                   "kpi-power-avg-val",  "MW",   "#10b981",
                                   sub_id="kpi-power-max-sub"),
                        _kpi_badge("kpi-eff-avg",    "Rendement moyen",
                                   "kpi-eff-avg-val",    "%",    "#38bdf8",
                                   sub_id="kpi-eff-vs-nom-sub"),
                        _kpi_badge("kpi-speed-avg",  "Vitesse moy.",
                                   "kpi-speed-avg-val",  "RPM",  "#818cf8",
                                   sub_id="kpi-speed-sub"),
                        _kpi_badge("kpi-alerts-cnt", "Alertes période",
                                   "kpi-alerts-cnt-val", "",     "#f59e0b",
                                   sub_id="kpi-alerts-crit-sub"),
                        _kpi_badge("kpi-degraded",   "Temps dégradé",
                                   "kpi-degraded-val",   "%",    "#ef4444",
                                   sub_id="kpi-degraded-sub"),
                        _kpi_badge("kpi-points",     "Points enregistrés",
                                   "kpi-points-val",     "",     "#64748b",
                                   sub_id="kpi-period-sub"),
                    ], className="kpi-row"),
                ], className="card", style={"marginBottom": "16px"}),

                # ══════════════════════════════════════════════════════════
                # JAUGES TEMPS RÉEL (déplacées depuis Dashboard)
                # ══════════════════════════════════════════════════════════
                html.Details([
                    html.Summary([
                        html.Span("⚡", style={"marginRight": "8px"}),
                        html.Span("Jauges temps réel", style={
                            "fontFamily": "Share Tech Mono", "fontSize": "11px",
                            "letterSpacing": "1.5px", "textTransform": "uppercase",
                            "color": "#64748b", "cursor": "pointer",
                        }),
                    ], style={"listStyle": "none", "display": "flex",
                              "alignItems": "center", "padding": "12px 20px",
                              "background": "var(--bg-card-alt)",
                              "borderRadius": "8px", "cursor": "pointer",
                              "border": "1px solid var(--border)",
                              "marginBottom": "8px",
                              "userSelect": "none"}),

                    html.Div([
                        _gauge_section(
                            "Paramètres critiques — vapeur HP / turbine / puissance",
                            _GAUGES_FAST, "#f97316",
                        ),
                        _gauge_section(
                            "Électrique — alternateur",
                            _GAUGES_SLOW_ELEC, "#10b981",
                        ),
                        _gauge_section(
                            "Vapeur BP — condenseur / barillet",
                            _GAUGES_SLOW_BP, "#38bdf8",
                        ),
                    ], style={"paddingTop": "12px"}),
                ], style={"marginBottom": "16px"}),

                # ══════════════════════════════════════════════════════════
                # FILTRES DATE & PARAMÈTRES
                # ══════════════════════════════════════════════════════════
                html.Div([

                    # Filtres rapides
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

                    # Plage manuelle
                    html.Div([
                        html.Div("Plage personnalisée", className="filter-label"),
                        html.Div([
                            dcc.Input(
                                id="date-start", type="date", value=None,
                                className="custom-input", style={"width": "145px"},
                            ),
                            html.Span("→", style={
                                "color": "var(--text3)", "fontSize": "12px",
                                "alignSelf": "center",
                            }),
                            dcc.Input(
                                id="date-end", type="date", value=today,
                                className="custom-input", style={"width": "145px"},
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

                # ── Graphique principal ───────────────────────────────────
                html.Div([
                    html.Div("Évolution temporelle multi-paramètres",
                             className="card-title"),
                    dcc.Graph(id="history-chart",
                              figure=create_empty_fig(320, "Chargement de l'historique..."),
                              config={"displayModeBar": True},
                              style={"height": "320px"}),
                ], className="card", style={"marginBottom": "16px"}),

                # ── Stats + Distribution ──────────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Statistiques descriptives", className="card-title"),
                        html.Div(id="stats-table"),
                    ], className="card", style={"flex": "3"}),

                    html.Div([
                        html.Div("Répartition des états", className="card-title"),
                        dcc.Graph(id="status-pie",
                                  figure=create_empty_fig(220, "Calcul des statuts..."),
                                  config={"displayModeBar": False},
                                  style={"height": "220px"}),
                    ], className="card", style={"flex": "2"}),

                ], style={"display": "flex", "gap": "16px", "marginBottom": "16px"}),

                # ── Tableau détaillé ──────────────────────────────────────
                html.Div([
                    html.Div("Journal de données détaillé", className="card-title"),
                    html.Div(id="history-data-table", style={"overflowX": "auto"}),
                ], className="card"),

            ], className="page-content"),

            dcc.Interval(id="interval-analysis", interval=10000, n_intervals=0),
        ], className="main-content"),
    ], className="main-content-wrap")