"""
components/gauges.py — Composants jauges SCADA réutilisables
"""
from dash import html, dcc
import plotly.graph_objects as go

GAUGE_CONFIGS = {
    "pressure_hp":    {"title": "Pression HP",      "unit": "bar",  "min": 40,  "max": 80,   "warn_low": 55,   "warn_high": 65,   "color": "#00b4ff"},
    "temperature_hp": {"title": "Température HP",   "unit": "°C",   "min": 400, "max": 550,  "warn_low": 440,  "warn_high": 500,  "color": "#ff7043"},
    "turbine_speed":  {"title": "Vitesse Turbine",  "unit": "RPM",  "min": 5500,"max": 7000, "warn_low": 6300, "warn_high": 6500, "color": "#aa80ff"},
    "active_power":   {"title": "Puissance Active", "unit": "MW",   "min": 0,   "max": 35,   "warn_low": None, "warn_high": 32,   "color": "#00e676"},
    "power_factor":   {"title": "Facteur cosφ",     "unit": "cosφ", "min": 0.7, "max": 1.0,  "warn_low": 0.80, "warn_high": 0.95, "color": "#ffd740"},
    "efficiency":     {"title": "Rendement",        "unit": "%",    "min": 60,  "max": 100,  "warn_low": 80,   "warn_high": None, "color": "#00e5ff"},
}


def make_gauge(value, cfg):
    color = cfg["color"]
    wl, wh = cfg.get("warn_low"), cfg.get("warn_high")
    if wl and value < wl: color = "#ffd740"
    if wh and value > wh: color = "#ffd740"
    if value < cfg["min"] * 0.92 or value > cfg["max"] * 1.08: color = "#ff3d57"

    steps = []
    mn, mx = cfg["min"], cfg["max"]
    if wl and wh:
        steps = [
            {"range": [mn, wl],  "color": "rgba(255,61,87,0.12)"},
            {"range": [wl, wh],  "color": "rgba(0,230,118,0.07)"},
            {"range": [wh, mx],  "color": "rgba(255,215,64,0.12)"},
        ]

    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        title={"text": f"{cfg['title']}<br><span style='font-size:10px;color:#3a5a7a'>{cfg['unit']}</span>",
               "font": {"size": 11, "color": "#6a96bb", "family": "Share Tech Mono"}},
        number={"font": {"size": 18, "color": color, "family": "Share Tech Mono"},
                "suffix": f" {cfg['unit']}"},
        gauge={
            "axis": {"range": [mn, mx], "tickcolor": "#1e3a5f",
                     "tickfont": {"size": 8, "color": "#3a5a7a", "family": "Share Tech Mono"}, "nticks": 5},
            "bar": {"color": color, "thickness": 0.22},
            "bgcolor": "rgba(0,0,0,0)", "borderwidth": 1, "bordercolor": "#1e3a5f",
            "steps": steps,
        },
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin={"t": 55, "b": 5, "l": 15, "r": 15}, height=155,
                      font={"family": "Share Tech Mono"})
    return fig


def gauge_card(gauge_id):
    return html.Div([
        dcc.Graph(id=gauge_id, config={"displayModeBar": False}, style={"height": "155px"}),
    ], className="card", style={"padding": "8px"})