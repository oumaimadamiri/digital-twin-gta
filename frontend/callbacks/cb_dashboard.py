"""
callbacks/cb_dashboard.py — Patches ciblés pour cb_dashboard.py existant

CORRECTIONS À APPLIQUER (remplacement de sections dans cb_dashboard.py) :

  1. Jauges : split en FAST (5 critiques, sur WS) + SLOW (9 secondaires, sur interval-slow 5s)
     → réduction de 14 → 5 graphiques mis à jour à 500ms
  2. Graphique RT : figure initialisée dans le layout (plus de reconstruction)

════════════════════════════════════════════════════════════════
INSTRUCTIONS D'APPLICATION :
  Remplacer dans cb_dashboard.py le callback update_gauges unique
  par les deux callbacks ci-dessous : update_gauges_fast + update_gauges_slow
════════════════════════════════════════════════════════════════
"""
import json
from datetime import datetime
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, Patch
from components.gauges import make_gauge, GAUGE_CONFIGS
from components.alert_banner import alerts_panel
from config import BACKEND

_session = requests.Session()

# ── Paramètres du graphique RT ────────────────────────────────────────────
_RT_PARAMS = {
    "active_power":   {"label": "P active (MW)",      "color": "#10b981", "scale": 1.0},
    "pressure_hp":    {"label": "P HP (bar)",         "color": "#f97316", "scale": 1.0},
    "turbine_speed":  {"label": "Vitesse (/100 RPM)", "color": "#818cf8", "scale": 0.01},
    "temperature_hp": {"label": "T HP (°C/10)",       "color": "#ef4444", "scale": 0.1},
    "efficiency":     {"label": "Rendement (%)",      "color": "#38bdf8", "scale": 1.0},
    "power_factor":   {"label": "cos φ (×10)",        "color": "#fbbf24", "scale": 10.0},
}

_BASE_RT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    margin={"t": 10, "b": 40, "l": 40, "r": 10},
    legend={"font": {"color": "#64748b", "size": 9},
            "bgcolor": "rgba(0,0,0,0)", "orientation": "h", "y": -0.35},
    xaxis={"tickfont": {"color": "#334155", "size": 8}, "gridcolor": "#0f2744",
           "showgrid": True, "color": "#1e293b", "tickformat": "%H:%M:%S", "type": "date"},
    yaxis={"tickfont": {"color": "#334155", "size": 8}, "gridcolor": "#0f2744",
           "showgrid": True, "color": "#1e293b"},
    font={"family": "Share Tech Mono"},
    hovermode="x unified",
    uirevision="realtime",
)

# ── 5 jauges critiques → mis à jour sur chaque push WS (500ms) ────────────
_GAUGES_FAST = ["pressure_hp", "temperature_hp", "active_power",
                "turbine_speed", "efficiency"]

# ── 9 jauges secondaires → mis à jour sur interval-slow (5s) ─────────────
_GAUGES_SLOW = ["steam_flow_hp", "reactive_power", "apparent_power",
                "power_factor", "current_a", "voltage",
                "pressure_bp_in", "pressure_bp_barillet", "steam_flow_condenser"]


def make_empty_rt_figure():
    """Figure RT vide initialisée avec toutes les traces.
    Appeler depuis dashboard.layout() pour éviter la reconstruction."""
    fig = go.Figure()
    for param, cfg in _RT_PARAMS.items():
        fig.add_trace(go.Scatter(
            x=[], y=[], name=cfg["label"],
            line={"color": cfg["color"], "width": 1.5},
            mode="lines",
        ))
    fig.update_layout(**_BASE_RT_LAYOUT)
    return fig


def _figure_has_traces(fig) -> bool:
    if fig is None:
        return False
    data = fig.get("data", [])
    return len(data) == len(_RT_PARAMS)


def register(app):

    # ── Horloge ──────────────────────────────────────────────────────
    @app.callback(
        Output("topbar-time", "children"),
        Input("interval-fast", "n_intervals"),
        Input("interval-slow",  "n_intervals"),
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
        colors = {"NORMAL": "#10b981", "DEGRADED": "#f59e0b", "CRITICAL": "#ef4444"}
        color  = colors.get(status, "#10b981")
        return html.Span(status, style={
            "color": color, "fontWeight": "700",
            "fontFamily": "var(--ui)", "fontSize": "11px", "letterSpacing": "1px",
        })

    # ── KPI Row ───────────────────────────────────────────────────────
    # @app.callback(
    #     Output("kpi-row", "children"),
    #     Input("store-current-data", "data"),
    #     State("url", "pathname"),
    #     prevent_initial_call=True,
    # )
    # def update_kpis(d, pathname):
    #     if pathname != "/":
    #         return no_update
    #     d = d or {}

    #     def badge(val, label, unit, cls, sub="", fmt=".1f"):
    #         return html.Div([
    #             html.Div(label, className="kpi-label"),
    #             html.Div([
    #                 html.Span(f"{val:{fmt}}", className="kpi-val-num"),
    #                 html.Span(unit, className="kpi-unit"),
    #             ], className="kpi-val"),
    #             html.Div(sub, className="kpi-sub") if sub else None,
    #         ], className=f"kpi-badge {cls}")

    #     def cls_range(val, lo, hi):
    #         if val < lo or val > hi:
    #             return "crit"
    #         margin = (hi - lo) * 0.15
    #         if val < lo + margin or val > hi - margin:
    #             return "warn"
    #         return "ok"

    #     p_cls  = cls_range(d.get("pressure_hp",  60),   55,   65)
    #     t_cls  = cls_range(d.get("temperature_hp",486),  420,  500)
    #     s_cls  = cls_range(d.get("turbine_speed",6435), 6300, 6550)
    #     pw_cls = ("crit" if d.get("active_power", 24) > 30
    #               else "warn" if d.get("active_power", 24) > 24 else "ok")
    #     pf_cls = cls_range(d.get("power_factor", 0.85), 0.82, 0.86)
    #     ef_cls = ("crit" if d.get("efficiency", 92) < 85
    #               else "warn" if d.get("efficiency", 92) < 88 else "ok")
    #     ia_cls = "crit" if d.get("current_a", 2254) > 3200 else "ok"
    #     pb_cls = "crit" if d.get("pressure_bp_barillet", 3.0) > 3.5 else "ok"

    #     return [
    #         badge(d.get("active_power",   0), "PUISSANCE ACTIVE",  "MW",  pw_cls,
    #               "Nominal 24 MW" if pw_cls == "ok" else "Dépassement !"),
    #         badge(d.get("turbine_speed",  0), "VITESSE TURBINE",   "RPM", s_cls,
    #               "6435 RPM cible" if s_cls == "ok" else "Hors plage", fmt=".0f"),
    #         badge(d.get("pressure_hp",    0), "PRESSION HP",       "bar", p_cls,
    #               "60 bar nominal" if p_cls == "ok" else "Écart"),
    #         badge(d.get("temperature_hp", 0), "TEMPÉRATURE HP",    "°C",  t_cls,
    #               "Design 486°C" if d.get("temperature_hp", 486) >= 460
    #               else "Opérat. 440°C", fmt=".0f"),
    #         badge(d.get("efficiency",     0), "RENDEMENT THERMO",  "%",   ef_cls,
    #               "Optimal" if ef_cls == "ok" else "Dégradé"),
    #         badge(d.get("power_factor",   0), "FACTEUR cos φ",     "",    pf_cls,
    #               "0.82–0.86 spec" if pf_cls == "ok" else "Hors plage", fmt=".3f"),
    #         badge(d.get("current_a",      0), "COURANT DE LIGNE",  "A",   ia_cls,
    #               "Normal" if ia_cls == "ok" else "Surintensité", fmt=".0f"),
    #         badge(d.get("pressure_bp_barillet", 3.0), "PRESS. BARILLET", "bar", pb_cls,
    #               "3 bar nominal" if pb_cls == "ok" else "Surpression !"),
    #     ]

    # ── FIX : 5 jauges CRITIQUES — sur chaque push WS ────────────────
    # (était 14 jauges toutes ensemble = 28 figures/s)
    @app.callback(
        [Output(f"gauge-{k}", "figure") for k in _GAUGES_FAST],
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_gauges_fast(d, pathname):
        if pathname != "/":
            return [no_update] * len(_GAUGES_FAST)
        d = d or {}
        return [
            make_gauge(d.get(k, GAUGE_CONFIGS[k]["min"] +
                             (GAUGE_CONFIGS[k]["max"] - GAUGE_CONFIGS[k]["min"]) * 0.5),
                       GAUGE_CONFIGS[k])
            for k in _GAUGES_FAST
        ]

    # ── FIX : 9 jauges SECONDAIRES — sur interval-slow (5s) ──────────
    # Réduit la charge CPU de ~72% (9/14 × moins fréquent × 10)
    @app.callback(
        [Output(f"gauge-{k}", "figure") for k in _GAUGES_SLOW],
        Input("interval-slow", "n_intervals"),
        State("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_gauges_slow(_, d, pathname):
        if pathname != "/":
            return [no_update] * len(_GAUGES_SLOW)
        d = d or {}
        return [
            make_gauge(d.get(k, GAUGE_CONFIGS[k]["min"] +
                             (GAUGE_CONFIGS[k]["max"] - GAUGE_CONFIGS[k]["min"]) * 0.5),
                       GAUGE_CONFIGS[k])
            for k in _GAUGES_SLOW
        ]

    # ── Graphique temps réel (FIX : Patch() sécurisé) ─────────────────
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
        if not d:
            return no_update
        if not _figure_has_traces(current_fig):
            return make_empty_rt_figure()

        patched = Patch()
        ts = d.get("timestamp", "")[:19]

        for i, (param, cfg) in enumerate(_RT_PARAMS.items()):
            val = d.get(param, 0) * cfg["scale"]
            existing_x = current_fig["data"][i].get("x") or []
            existing_y = current_fig["data"][i].get("y") or []
            xs = list(existing_x) + [ts]
            ys = list(existing_y) + [val]
            if len(xs) > 180:
                xs, ys = xs[-180:], ys[-180:]
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
            r = _session.get(
                f"{BACKEND}/settings/alerts?limit=10&only_active=true", timeout=1
            )
            return alerts_panel(r.json())
        except Exception:
            return alerts_panel([])

    # ── Acquittement alertes ──────────────────────────────────────────
    from dash import MATCH, callback_context as ctx

    @app.callback(
        Output({"type": "ack-btn", "index": MATCH}, "children"),
        Output({"type": "ack-btn", "index": MATCH}, "disabled"),
        Input({"type": "ack-btn", "index": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
    def acknowledge_alert(n_clicks):
        if not n_clicks:
            return no_update, no_update
        if not ctx.triggered:
            return no_update, no_update
        try:
            btn_id   = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
            alert_id = btn_id["index"]
            r = _session.post(
                f"{BACKEND}/settings/alerts/{alert_id}/acknowledge", timeout=1
            )
            if r.status_code == 200:
                return "OK", True
        except Exception as e:
            print("Erreur acquittement:", e)
        return "Erreur", False

    # ── Synoptique (clientside_callback JS) ───────────────────────────
    app.clientside_callback(
        """function(data, pathname) {
            if (pathname !== '/') return window.dash_clientside.no_update;
            if (!data || Object.keys(data).length === 0)
                return window.dash_clientside.no_update;
            if (typeof window.patchGtaSynoptic === 'function')
                window.patchGtaSynoptic(data);
            return window.dash_clientside.no_update;
        }""",
        Output("syn-patch-tick", "data"),
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )