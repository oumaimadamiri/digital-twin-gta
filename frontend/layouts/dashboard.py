"""
layouts/dashboard.py — Vue Dashboard temps réel SCADA
Organisation : Synoptique → KPIs → Jauges par section (Thermo / Électrique / BP)
"""
from dash import html, dcc
from components.sidebar import create_sidebar, create_topbar
from components.gauges import gauge_card, GAUGE_CONFIGS


def _gauge_section(title, gauge_keys, color):
    """Groupe de jauges avec titre de section."""
    return html.Div([
        html.Div([
            html.Span(style={
                "display":       "inline-block",
                "width":         "8px",
                "height":        "8px",
                "borderRadius":  "50%",
                "background":    color,
                "marginRight":   "8px",
                "verticalAlign": "middle",
            }),
            html.Span(title, style={
                "color":      "#64748b",
                "fontSize":   "10px",
                "fontFamily": "Share Tech Mono",
                "letterSpacing": "1.5px",
                "textTransform": "uppercase",
            }),
        ], style={"marginBottom": "8px", "paddingLeft": "4px"}),
        html.Div(
            [gauge_card(f"gauge-{k}") for k in gauge_keys],
            style={
                "display":             "grid",
                "gridTemplateColumns": f"repeat({len(gauge_keys)}, 1fr)",
                "gap":                 "8px",
            },
        ),
    ], style={"marginBottom": "20px"})


def layout():
    return html.Div([
        create_sidebar(active_path="/"),
        html.Div([
            create_topbar("Tableau de Bord", "Surveillance Temps Réel"),

            html.Div([

                # ── KPI Row ────────────────────────────────────────────────
                html.Div(id="kpi-row", className="kpi-row",
                         style={"marginTop": "16px", "marginBottom": "20px"}),

                # ── Synoptique pleine largeur ──────────────────────────────
                html.Div([
                    html.Div(id="gta-synoptic"),
                ], style={"marginBottom": "20px"}),

                # ── Graphique temps réel ───────────────────────────────────
                html.Div([
                    html.Div("Tendances Temps Réel", className="card-title"),
                    dcc.Graph(
                        id="realtime-chart",
                        config={"displayModeBar": False},
                        style={"height": "200px"},
                    ),
                ], className="card", style={"marginBottom": "20px"}),

                # ── Section Thermodynamique ────────────────────────────────
                _gauge_section(
                    "Thermodynamique — Vapeur HP / Turbine",
                    ["pressure_hp", "temperature_hp", "steam_flow_hp",
                     "turbine_speed", "efficiency"],
                    "#f97316",
                ),

                # ── Section Électrique ─────────────────────────────────────
                _gauge_section(
                    "Électrique — Alternateur",
                    ["active_power", "reactive_power", "apparent_power",
                     "power_factor", "current_a", "voltage"],
                    "#10b981",
                ),

                # ── Section BP / Condenseur ────────────────────────────────
                _gauge_section(
                    "Vapeur BP — Condenseur / Barillet",
                    ["pressure_bp_in", "pressure_bp_barillet",
                     "steam_flow_condenser"],
                    "#38bdf8",
                ),

                # ── Alertes ────────────────────────────────────────────────
                html.Div([
                    html.Div("Alertes Actives", className="card-title"),
                    html.Div(id="alerts-panel"),
                ], className="card", style={"marginBottom": "20px"}),

            ], className="page-content"),
        ], className="main-content"),
    ], className="main-content-wrap")