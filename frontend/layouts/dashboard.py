"""
layouts/dashboard.py — Vue Dashboard temps réel SCADA

CORRECTIONS :
  1. Figure RT initialisée dans le layout (figure=make_empty_rt_figure())
     → plus de reconstruction à chaque push WS si traces manquantes
  2. Jauges : regroupées en sections fast/slow cohérentes avec cb_dashboard.py
     (les IDs des gauge-X doivent tous exister dans le DOM même si peu mis à jour)
  3. create_topbar supprimé (seul ai_module.py l'utilisait, déjà corrigé)
"""
from dash import html, dcc
from components.sidebar import create_sidebar
from components.gauges import gauge_card, GAUGE_CONFIGS
from components.gta_synoptic import create_gta_synoptic_static

# Import de la figure vide depuis cb_dashboard pour éviter la duplication
# (cb_dashboard.py exporte make_empty_rt_figure())
from callbacks.cb_dashboard import make_empty_rt_figure


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
            [gauge_card(f"gauge-{k}") for k in gauge_keys],
            style={
                "display": "grid",
                "gridTemplateColumns": f"repeat({len(gauge_keys)}, 1fr)",
                "gap": "8px",
            },
        ),
    ], style={"marginBottom": "20px"})


def layout():
    return html.Div([
        create_sidebar(active_path="/"),
        html.Div([
            html.Div([

                # ── Synoptique + panneau état système ──────────────────────
                html.Div(
                    style={"position": "relative", "marginBottom": "20px"},
                    children=[
                        html.Div(
                            id="gta-synoptic",
                            children=[create_gta_synoptic_static()],
                        ),
                        # Panneau état superposé en bas à droite
                        html.Div(
                            id="dash-state-panel",
                            style={
                                "position":       "absolute",
                                "bottom":         "12px",
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

                # ── Graphique temps réel ───────────────────────────────────
                html.Div([
                    html.Div("Tendances temps réel", className="card-title"),
                    dcc.Graph(
                        id="realtime-chart",
                        config={"displayModeBar": False},
                        style={"height": "320px"},
                        figure=make_empty_rt_figure(),
                    ),
                ], className="card", style={"marginBottom": "20px"}),

                # ── Jauges CRITIQUES (fast — mises à jour sur WS 500ms) ────
                _gauge_section(
                    "Paramètres critiques — vapeur HP / turbine / puissance",
                    ["pressure_hp", "temperature_hp", "active_power",
                     "turbine_speed", "efficiency"],
                    "#f97316",
                ),

                # ── Jauges SECONDAIRES (slow — mises à jour sur 5s) ────────
                _gauge_section(
                    "Électrique — alternateur",
                    ["reactive_power", "apparent_power", "power_factor",
                     "current_a", "voltage"],
                    "#10b981",
                ),

                _gauge_section(
                    "Vapeur BP — condenseur / barillet",
                    ["steam_flow_hp", "pressure_bp_in", "pressure_bp_barillet",
                     "steam_flow_condenser"],
                    "#38bdf8",
                ),

                # ── Alertes ────────────────────────────────────────────────
                html.Div([
                    html.Div("Alertes actives", className="card-title"),
                    html.Div(id="alerts-panel"),
                ], className="card", style={"marginBottom": "20px"}),

            ], className="page-content"),
        ], className="main-content"),
    ], className="main-content-wrap")