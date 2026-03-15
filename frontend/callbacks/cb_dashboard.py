"""
callbacks/cb_dashboard.py — Callbacks temps réel du dashboard SCADA
Mise à jour : nouveaux KPIs (I, Q, S, P_barillet, Q_cond), jauges par section,
              graphique étendu à 6 courbes.
"""
import json
from datetime import datetime
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, callback, html, no_update, Patch
from components.gauges import make_gauge, GAUGE_CONFIGS
from components.gta_synoptic import create_gta_synoptic
from components.alert_banner import alerts_panel
from config import BACKEND

_session = requests.Session()

# ── Courbes du graphique temps réel ──────────────────────────────────
_RT_PARAMS = {
    "active_power":    {"label": "P active (MW)",    "color": "#10b981", "scale": 1.0},
    "pressure_hp":     {"label": "P HP (bar)",       "color": "#f97316", "scale": 1.0},
    "turbine_speed":   {"label": "Vitesse (/100 RPM)","color": "#818cf8","scale": 0.01},
    "temperature_hp":  {"label": "T HP (°C/10)",     "color": "#ef4444", "scale": 0.1},
    "efficiency":      {"label": "Rendement (%)",    "color": "#38bdf8", "scale": 1.0},
    "power_factor":    {"label": "cos φ (×10)",      "color": "#fbbf24", "scale": 10.0},
}

_BASE_RT_LAYOUT = dict(
    paper_bgcolor = "rgba(0,0,0,0)",
    plot_bgcolor  = "rgba(0,0,0,0)",
    margin        = {"t": 10, "b": 30, "l": 40, "r": 10},
    legend        = {"font": {"color": "#64748b", "size": 9},
                     "bgcolor": "rgba(0,0,0,0)", "orientation": "h",
                     "y": -0.25},
    xaxis = {"tickfont": {"color": "#334155", "size": 8},
             "gridcolor": "#0f2744", "showgrid": True, "color": "#1e3a5f"},
    yaxis = {"tickfont": {"color": "#334155", "size": 8},
             "gridcolor": "#0f2744", "showgrid": True, "color": "#1e3a5f"},
    font      = {"family": "Share Tech Mono"},
    hovermode = "x unified",
    uirevision= "realtime",
)


def _make_empty_rt_figure():
    fig = go.Figure()
    for param, cfg in _RT_PARAMS.items():
        fig.add_trace(go.Scatter(
            x=[], y=[], name=cfg["label"],
            line={"color": cfg["color"], "width": 1.5},
            mode="lines",
        ))
    fig.update_layout(**_BASE_RT_LAYOUT)
    return fig


def register(app):

    # ── Horloge ───────────────────────────────────────────────────────
    @app.callback(
        Output("topbar-time", "children"),
        Input("interval-fast", "n_intervals"),
    )
    def update_clock(_):
        return datetime.now().strftime("%d/%m/%Y  %H:%M:%S")

    # ── Status Pill ───────────────────────────────────────────────────
    @app.callback(
        Output("topbar-status-pill", "children"),
        Input("store-current-data", "data"),
        prevent_initial_call=True,
    )
    def update_status_pill(d):
        d = d or {}
        status = d.get("status", "NORMAL")
        return html.Span(status, className=f"status-pill {status.lower()}")

    # ── KPI Row étendu ────────────────────────────────────────────────
    @app.callback(
        Output("kpi-row", "children"),
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_kpis(d, pathname):
        if pathname != "/":
            return no_update
        d = d or {}

        def badge(val, label, unit, cls, sub="", sub_icon="", fmt=".1f"):
            return html.Div([
                html.Div(label, className="kpi-label"),
                html.Div([
                    html.Span(f"{val:{fmt}}", className="kpi-val-num"),
                    html.Span(unit, className="kpi-unit"),
                ], className="kpi-val"),
                html.Div([
                    html.Span(sub_icon, style={"marginRight": "4px"}),
                    html.Span(sub),
                ], className="kpi-sub") if sub else None,
            ], className=f"kpi-badge {cls}")

        def cls_range(val, lo, hi):
            if val < lo or val > hi: return "crit"
            margin = (hi - lo) * 0.15
            if val < lo + margin or val > hi - margin: return "warn"
            return "ok"

        def sub(c, ok, warn, crit):
            return [ok, "↗"][c == "ok"] if c == "ok" else \
                   ([warn, "⚠"][c == "warn"] if c == "warn" else [crit, "↓"])

        # Calcul des classes
        p_cls  = cls_range(d.get("pressure_hp",  60),   55,   65)
        t_cls  = cls_range(d.get("temperature_hp",486),  420,  500)
        s_cls  = cls_range(d.get("turbine_speed",6435), 6300, 6550)
        pw_cls = "crit" if d.get("active_power",24) > 30 else \
                 "warn" if d.get("active_power",24) > 24 else "ok"
        pf_cls = cls_range(d.get("power_factor",0.85),  0.82,  0.86)
        ef_cls = "crit" if d.get("efficiency",92) < 85 else \
                 "warn" if d.get("efficiency",92) < 88 else "ok"
        ia_cls = "crit" if d.get("current_a",2254) > 3200 else "ok"
        pb_cls = "crit" if d.get("pressure_bp_barillet",3.0) > 3.5 else "ok"

        return [
            badge(d.get("active_power",   0),  "PUISSANCE ACTIVE",    "MW",    pw_cls,
                  "Nominal 24 MW" if pw_cls=="ok" else "Dépassement !"),
            badge(d.get("turbine_speed",  0),  "VITESSE TURBINE",     "RPM",   s_cls,
                  "6435 RPM cible" if s_cls=="ok" else "Hors plage", fmt=".0f"),
            badge(d.get("pressure_hp",    0),  "PRESSION HP",         "bar",   p_cls,
                  "60 bar nominal" if p_cls=="ok" else "Écart"),
            badge(d.get("temperature_hp", 0),  "TEMPÉRATURE HP",      "°C",    t_cls,
                  "Design 486°C" if d.get("temperature_hp",486) >= 460 else
                  "⚠ Opérat. 440°C", fmt=".0f"),
            badge(d.get("efficiency",     0),  "RENDEMENT THERMO",    "%",     ef_cls,
                  "Optimal" if ef_cls=="ok" else "Dégradé"),
            badge(d.get("power_factor",   0),  "FACTEUR cos φ",       "",      pf_cls,
                  "0.82–0.86 spec" if pf_cls=="ok" else "Hors plage", fmt=".3f"),
            badge(d.get("current_a",      0),  "COURANT DE LIGNE",    "A",     ia_cls,
                  "Normal" if ia_cls=="ok" else "Surintensité", fmt=".0f"),
            badge(d.get("pressure_bp_barillet",3.0), "PRESS. BARILLET", "bar", pb_cls,
                  "3 bar nominal" if pb_cls=="ok" else "Surpression !"),
        ]

    # ── Jauges par section ────────────────────────────────────────────
    @app.callback(
        [Output(f"gauge-{k}", "figure") for k in GAUGE_CONFIGS],
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_gauges(d, pathname):
        if pathname != "/":
            return [no_update] * len(GAUGE_CONFIGS)
        d = d or {}
        return [make_gauge(d.get(k, cfg["min"] + (cfg["max"]-cfg["min"])*0.5), cfg)
                for k, cfg in GAUGE_CONFIGS.items()]

    # ── Graphique temps réel (6 courbes) ─────────────────────────────
    @app.callback(
        Output("realtime-chart", "figure"),
        Input("store-current-data", "data"),
        State("realtime-chart", "figure"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_realtime_chart(d, current_fig, pathname):
        if pathname != "/":
            return no_update
        if not d or current_fig is None:
            return _make_empty_rt_figure()

        patched = Patch()
        ts = d.get("timestamp", "")[:19]

        for i, (param, cfg) in enumerate(_RT_PARAMS.items()):
            val = d.get(param, 0) * cfg["scale"]
            xs  = current_fig["data"][i]["x"] + [ts]
            ys  = current_fig["data"][i]["y"] + [val]
            if len(xs) > 90:
                xs, ys = xs[-90:], ys[-90:]
            patched["data"][i]["x"] = xs
            patched["data"][i]["y"] = ys

        return patched

    # ── Alertes ────────────────────────────────────────────────────────
    @app.callback(
        Output("alerts-panel", "children"),
        Input("interval-slow", "n_intervals"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_alerts(_, pathname):
        if pathname != "/":
            return no_update
        try:
            r = _session.get(f"{BACKEND}/settings/alerts?limit=10&only_active=true", timeout=1)
            return alerts_panel(r.json())
        except Exception:
            return alerts_panel([])

    # ── Synoptique ─────────────────────────────────────────────────────
    @app.callback(
        Output("gta-synoptic", "children"),
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_synoptic(d, pathname):
        if pathname != "/":
            return no_update
        return create_gta_synoptic(d or {})