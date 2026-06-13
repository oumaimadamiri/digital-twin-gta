"""
layouts/analysis.py — Analyse & Historique

MODIFICATIONS :
  1. Bouton [● LIVE] ajouté dans la barre de filtres rapides.
     En mode LIVE, le graphe d'évolution temporelle se comporte exactement
     comme l'ancien graphe Dashboard (source = store-history WS, fenêtre 2m30s).
  2. En mode HISTORY (défaut), comportement inchangé (HTTP history, date picker).
  3. L'indicateur de mode (pill coloré) s'affiche dans le header du graphe.
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.gauges import create_empty_fig
from config import BACKEND
from datetime import date

_VIEW_PARAM_OPTIONS = [
    {"label": "Pression HP (bar)", "value": "pressure_hp"},
    {"label": "Température HP (°C)", "value": "temperature_hp"},
    {"label": "Vitesse turbine (RPM)", "value": "turbine_speed"},
    {"label": "Puissance active (MW)", "value": "active_power"},
    {"label": "Facteur cosφ", "value": "power_factor"},
    {"label": "Rendement (%)", "value": "efficiency"},
    {"label": "Débit vapeur HP (T/h)", "value": "steam_flow_hp"},
    {"label": "Courant (A)", "value": "current_a"},
]
def _info_icon(text):
    return html.Span([
        "i",
        html.Div(text, className="info-tooltip"),
    ], className="info-icon")

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
                # BANDE KPI
                # ══════════════════════════════════════════════════════════
                html.Div([
                    html.Div([
                        html.Span("Indicateurs sur la période sélectionnée",
                                  className="card-title", style={"marginBottom": "0"}),
                        _info_icon(
                            "Statistiques agrégées sur la période choisie via les filtres "
                            "rapides ou la plage de dates : puissance moyenne, rendement, "
                            "vitesse, alertes générées, temps passé en état dégradé et "
                            "nombre de points enregistrés."
                        ),
                    ],style={"display": "flex", "alignItems": "center", "gap": "6px", "marginBottom": "12px"}),
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
                # FILTRES DATE & PARAMÈTRES
                # ══════════════════════════════════════════════════════════
                html.Div([

                    # ── Filtres rapides (LIVE + 1h/6h/24h/7j/Tout) ────────
                    html.Div([
                        html.Div("Période rapide", className="filter-label"),
                        html.Div([
                            # Bouton LIVE — source WebSocket (temps réel)
                            html.Button(
                                [
                                    html.Span("●", style={
                                        "color": "#10b981", "marginRight": "5px",
                                        "fontSize": "10px",
                                    }),
                                    html.Span("LIVE"),
                                ],
                                id="qf-live",
                                className="btn btn-outline",
                                style={"fontSize": "11px", "padding": "6px 12px",
                                       "display": "inline-flex", "alignItems": "center",
                                       "borderColor": "#10b981", "color": "#10b981"},
                            ),
                            # Séparateur
                            html.Span("│", style={"color": "#1e3a5f", "alignSelf": "center"}),
                            # Boutons historiques
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
                        ], style={"display": "flex", "gap": "6px", "flexWrap": "wrap",
                                  "alignItems": "center"}),
                    ], style={"flex": "0 0 auto"}),

                    # ── Plage manuelle ─────────────────────────────────────
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

                    # ── Paramètres (filtre CSV uniquement — indépendant de la vue graphe) ─
                    html.Div([
                        html.Div("Paramètres (filtre CSV)", className="filter-label"),
                        dcc.Dropdown(id="param-selector",
                            options=[
                                {"label": "Pression HP (bar)",     "value": "pressure_hp"},
                                {"label": "Température HP (°C)",   "value": "temperature_hp"},
                                {"label": "Vitesse turbine (RPM)", "value": "turbine_speed"},
                                {"label": "Puissance active (MW)", "value": "active_power"},
                                {"label": "Facteur cosφ",          "value": "power_factor"},
                                {"label": "Rendement (%)",         "value": "efficiency"},
                                {"label": "Débit vapeur HP (T/h)", "value": "steam_flow_hp"},
                                {"label": "Courant (A)",           "value": "current_a"},
                            ],
                            value=[],
                            placeholder="Vide = toutes les colonnes",
                            multi=True,
                            className="custom-dropdown",
                        ),
                    ], style={"flex": "2"}),

                    # ── Actions ────────────────────────────────────────────
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

                # ── Graphique principal (LIVE ou HISTORY) ─────────────────
                html.Div([
                    # Header avec sélecteur mono-paramètre + indicateur de mode
                    html.Div([
                        html.Div("Évolution temporelle",
                                 className="card-title", style={"marginBottom": "0"}),
                        html.Div([
                            html.Span("Vue :", style={
                                "color": "#64748b", "fontSize": "10px",
                                "fontFamily": "Share Tech Mono", "letterSpacing": "1px",
                                "marginRight": "8px",
                            }),
                            dcc.Dropdown(
                                id="param-view",
                                options=_VIEW_PARAM_OPTIONS,
                                value="active_power",
                                clearable=False,
                                searchable=False,
                                className="custom-dropdown",
                                style={"width": "230px", "fontSize": "12px"},
                            ),
                        ], style={"display": "flex", "alignItems": "center", "marginLeft": "auto",
                                  "marginRight": "16px"}),
                        # Indicateur de mode — mis à jour par callback
                        html.Div(id="analysis-mode-indicator", children=[
                            html.Span("●", style={
                                "color": "#334155", "marginRight": "5px", "fontSize": "10px",
                            }),
                            html.Span("HISTORIQUE", style={
                                "color": "#334155", "fontSize": "10px",
                                "fontFamily": "Share Tech Mono", "letterSpacing": "1px",
                            }),
                        ], style={"display": "flex", "alignItems": "center"}),
                    ], style={"display": "flex", "justifyContent": "space-between",
                              "alignItems": "center", "marginBottom": "12px", "gap": "16px"}),

                    dcc.Graph(id="history-chart",
                              figure=create_empty_fig(320, "Sélectionnez une période ou LIVE"),
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
                        html.Div([
                            html.Span("Répartition des états", className="card-title", style={"marginBottom": "0"}),
                            _info_icon(
                                "Pourcentage du temps passé par la machine dans chaque statut "
                                "(NORMAL / DÉGRADÉ / CRITIQUE) sur la période sélectionnée "
                                "ci-dessus (plage de dates ou filtre rapide 1h/6h/24h/7j/Tout)."
                            ),
                        ], style={"display": "flex", "alignItems": "center", "gap": "6px", "marginBottom": "8px"}),
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

            # Plage exacte (datetime) pour export CSV des filtres rapides
            dcc.Store(id="csv-export-range", data=None),
            dcc.Interval(id="interval-analysis", interval=10000, n_intervals=0),
        ], className="main-content"),
    ], className="main-content-wrap")