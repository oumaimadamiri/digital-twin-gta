"""
components/gauges.py — Jauges SCADA étendues
Ajouts : current_a, reactive_power, apparent_power, pressure_bp_barillet,
         steam_flow_condenser, pressure_condenser
"""
from dash import html, dcc
import plotly.graph_objects as go

GAUGE_CONFIGS = {
    # ── Thermodynamique ──
    "pressure_hp": {
        "title": "Pression HP", "unit": "bar",
        "min": 40, "max": 80, "warn_low": 55, "warn_high": 65, "color": "#f97316",
    },
    "temperature_hp": {
        "title": "Température HP", "unit": "°C",
        "min": 380, "max": 540, "warn_low": 420, "warn_high": 500, "color": "#ef4444",
        "ref_line": 486,   # T design
    },
    "turbine_speed": {
        "title": "Vitesse Turbine", "unit": "RPM",
        "min": 5500, "max": 7000, "warn_low": 6300, "warn_high": 6550, "color": "#818cf8",
    },
    "steam_flow_hp": {
        "title": "Débit Vapeur HP", "unit": "T/h",
        "min": 60, "max": 140, "warn_low": 100, "warn_high": 130, "color": "#f97316",
    },
    # ── Puissance ──
    "active_power": {
        "title": "Puissance Active", "unit": "MW",
        "min": 0, "max": 35, "warn_low": None, "warn_high": 30, "color": "#10b981",
        "trip_line": 32,   # trip à 32 MW
    },
    "reactive_power": {
        "title": "Puissance Réactive", "unit": "MVAR",
        "min": 0, "max": 35, "warn_low": None, "warn_high": 28, "color": "#818cf8",
    },
    "apparent_power": {
        "title": "Puissance Apparente", "unit": "MVA",
        "min": 0, "max": 45, "warn_low": None, "warn_high": 41, "color": "#fbbf24",
    },
    "power_factor": {
        "title": "Facteur cos φ", "unit": "cosφ",
        "min": 0.70, "max": 1.0, "warn_low": 0.82, "warn_high": 0.86, "color": "#fbbf24",
    },
    # ── Électrique ──
    "current_a": {
        "title": "Courant de Ligne", "unit": "A",
        "min": 0, "max": 4000, "warn_low": None, "warn_high": 3200, "color": "#38bdf8",
    },
    "voltage": {
        "title": "Tension Nominale", "unit": "kV",
        "min": 9.0, "max": 12.0, "warn_low": 9.975, "warn_high": 11.025, "color": "#38bdf8",
    },
    # ── BP / Condenseur ──
    "pressure_bp_in": {
        "title": "Pression BP Entrée", "unit": "bar",
        "min": 2.0, "max": 8.0, "warn_low": 3.5, "warn_high": 6.0, "color": "#38bdf8",
    },
    "pressure_bp_barillet": {
        "title": "Pression BP Barillet", "unit": "bar",
        "min": 0.0, "max": 5.0, "warn_low": None, "warn_high": 3.5, "color": "#a78bfa",
    },
    "steam_flow_condenser": {
        "title": "Débit Condenseur", "unit": "T/h",
        "min": 30, "max": 100, "warn_low": 50, "warn_high": 85, "color": "#38bdf8",
    },
    # ── Rendement ──
    "efficiency": {
        "title": "Rendement Thermo.", "unit": "%",
        "min": 60, "max": 100, "warn_low": 85, "warn_high": None, "color": "#10b981",
    },
}


def make_gauge(value, cfg):
    color  = cfg["color"]
    wl, wh = cfg.get("warn_low"), cfg.get("warn_high")
    mn, mx = cfg["min"], cfg["max"]

    # Couleur alarme
    if wl and value < wl:  color = "#f59e0b"
    if wh and value > wh:  color = "#f59e0b"
    if value < mn * 0.88 or (mx > 0 and value > mx * 1.08):
        color = "#ef4444"

    # Zones colorées
    steps = []
    if wl and wh:
        steps = [
            {"range": [mn, wl],  "color": "rgba(239,68,68,0.10)"},
            {"range": [wl, wh],  "color": "rgba(16,185,129,0.07)"},
            {"range": [wh, mx],  "color": "rgba(245,158,11,0.10)"},
        ]
    elif wh:
        steps = [
            {"range": [mn, wh],  "color": "rgba(16,185,129,0.07)"},
            {"range": [wh, mx],  "color": "rgba(245,158,11,0.10)"},
        ]
    elif wl:
        steps = [
            {"range": [mn, wl],  "color": "rgba(239,68,68,0.10)"},
            {"range": [wl, mx],  "color": "rgba(16,185,129,0.07)"},
        ]

    # Ligne de seuil critique (trip ou design)
    threshold = None
    if cfg.get("trip_line"):
        threshold = {"line": {"color": "#ef4444", "width": 3}, "thickness": 0.75,
                     "value": cfg["trip_line"]}
    elif cfg.get("ref_line"):
        threshold = {"line": {"color": "#f59e0b", "width": 2}, "thickness": 0.6,
                     "value": cfg["ref_line"]}

    fig = go.Figure(go.Indicator(
        mode  = "gauge+number",
        value = value,
        title = {
            "text": (
                f"{cfg['title']}<br>"
                f"<span style='font-size:9px;color:#475569'>{cfg['unit']}</span>"
            ),
            "font": {"size": 11, "color": "#64748b", "family": "Share Tech Mono"},
        },
        number = {
            "font": {"size": 17, "color": color, "family": "Share Tech Mono"},
            "suffix": f" {cfg['unit']}",
        },
        gauge = {
            "axis": {
                "range":    [mn, mx],
                "tickcolor": "#0f2744",
                "tickfont":  {"size": 8, "color": "#334155", "family": "Share Tech Mono"},
                "nticks":    5,
            },
            "bar":         {"color": color, "thickness": 0.20},
            "bgcolor":     "rgba(0,0,0,0)",
            "borderwidth": 1,
            "bordercolor": "#0f2744",
            "steps":       steps,
            **({"threshold": threshold} if threshold else {}),
        },
    ))
    fig.update_layout(
        paper_bgcolor = "rgba(0,0,0,0)",
        plot_bgcolor  = "rgba(0,0,0,0)",
        margin        = {"t": 55, "b": 5, "l": 12, "r": 12},
        height        = 155,
        font          = {"family": "Share Tech Mono"},
    )
    return fig


def gauge_card(gauge_id):
    return html.Div(
        [dcc.Graph(id=gauge_id, config={"displayModeBar": False},
                   style={"height": "155px"})],
        className="card",
        style={"padding": "6px"},
    )