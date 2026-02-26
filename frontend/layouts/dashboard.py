"""
layouts/dashboard.py — Vue Dashboard temps réel
"""
from dash import html, dcc
from components.sidebar import create_sidebar, create_topbar
from components.gauges import gauge_card, GAUGE_CONFIGS


def layout():
    return html.Div([
        create_sidebar(active_path="/"),
        html.Div([
            create_topbar("Tableau de Bord", "Surveillance Temps Réel"),

            html.Div([
                # ── Note d'information
                html.Div([
                    html.Span("💡", style={"marginRight": "8px"}),
                    html.Span("Cliquez sur un composant", style={"color": "var(--blue-bright)"}),
                    html.Span(" du schéma pour afficher ses paramètres détaillés.", style={"color": "var(--text3)"})
                ], style={"padding": "12px 0", "borderBottom": "1px solid var(--border)", "fontSize": "12px", "display": "flex", "alignItems": "center"}),

                # ── KPIs principaux (Bandeau horizontal) ─────────────────────────
                html.Div(id="kpi-row", className="kpi-row", style={"marginTop": "16px", "marginBottom": "24px"}),

                # ── Synoptique et Légende (Pleine largeur) ─────────────────────
                html.Div([
                    html.Div(id="gta-synoptic"),
                ], style={"position": "relative", "width": "100%"}),

                # ... dashboards widgets here ...
            ], className="page-content"),

        ], className="main-content"),
    ], className="main-content-wrap")
