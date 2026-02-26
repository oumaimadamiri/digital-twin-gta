"""
callbacks/cb_dashboard.py — Callbacks temps réel du dashboard
Optimisé :
  - prevent_initial_call sur tous les callbacks secondaires
  - Graphique temps réel : extendData au lieu de reconstruire la Figure entière
  - Jauges : utilisation de Patch() pour mise à jour partielle
  - Suppression du code mort (bloc `if False`)
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

# Session HTTP réutilisable
_session = requests.Session()

# ── Constantes graphique temps réel ──────────────────────────────────
_RT_COLORS = {
    "active_power":  "#00e676",
    "pressure_hp":   "#00b4ff",
    "turbine_speed": "#aa80ff",
    "temperature_hp":"#ff7043",
}
_RT_LABELS = {
    "active_power":  "Puissance (MW)",
    "pressure_hp":   "Pression HP (bar)",
    "turbine_speed": "Vitesse RPM /100",
    "temperature_hp":"Temp HP (°C)",
}

# Layout de base pour le graphique temps réel (construit une seule fois)
_BASE_RT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    margin={"t": 10, "b": 30, "l": 40, "r": 10},
    legend={"font": {"color": "#6a96bb", "size": 10}, "bgcolor": "rgba(0,0,0,0)"},
    xaxis={"tickfont": {"color": "#3a5a7a", "size": 9}, "gridcolor": "#1e3a5f33",
           "showgrid": True, "color": "#1e3a5f"},
    yaxis={"tickfont": {"color": "#3a5a7a", "size": 9}, "gridcolor": "#1e3a5f33",
           "showgrid": True, "color": "#1e3a5f"},
    font={"family": "Share Tech Mono"},
    hovermode="x unified",
    uirevision="realtime",   # ← Empêche le reset du zoom/pan par l'utilisateur
)


def _make_empty_rt_figure():
    """Crée la figure de base avec toutes les traces vides."""
    fig = go.Figure()
    for param, color in _RT_COLORS.items():
        fig.add_trace(go.Scatter(
            x=[], y=[], name=_RT_LABELS[param],
            line={"color": color, "width": 1.5},
            mode="lines",
        ))
    fig.update_layout(**_BASE_RT_LAYOUT)
    return fig


def register(app):

    # ── Horloge ──────────────────────────────────────────────────────
    @app.callback(
        Output("topbar-time", "children"),
        Input("interval-fast", "n_intervals"),
    )
    def update_clock(_):
        return datetime.now().strftime("%d/%m/%Y  %H:%M:%S")

    # ── Status Pill (Global) ──────────────────────────────────────────
    @app.callback(
        Output("topbar-status-pill", "children"),
        Input("store-current-data", "data"),
        prevent_initial_call=True,
    )
    def update_status_pill(d):
        d = d or {}
        status = d.get("status", "NORMAL")
        css    = status.lower()
        return html.Span(status, className=f"status-pill {css}")

    # ── KPI Row (Dashboard only) ──────────────────────────────────────
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

        def badge(val, label, unit, cls, sub="", sub_icon=""):
            return html.Div([
                html.Div(label, className="kpi-label"),
                html.Div([
                    html.Span(f"{val:.1f}", className="kpi-val-num"),
                    html.Span(unit, className="kpi-unit")
                ], className="kpi-val"),
                html.Div([
                    html.Span(sub_icon, style={"marginRight": "4px"}),
                    html.Span(sub)
                ], className="kpi-sub") if sub else None,
            ], className=f"kpi-badge {cls}")

        def get_cls(val, lo, hi):
            if val < lo or val > hi: return "crit"
            # Marge d'alerte : 20% de l'étendue du range de sécurité
            margin = (hi - lo) * 0.2
            if val < (lo + margin) or val > (hi - margin): return "warn"
            return "ok"

        def get_sub(cls, ok_text, warn_text, crit_text):
            if cls == "ok": return ok_text, "↗"
            if cls == "warn": return warn_text, "⚠"
            return crit_text, "↓"

        p_hp_cls   = get_cls(d.get("pressure_hp", 60), 55, 65)
        p_hp_sub   = get_sub(p_hp_cls, "Consigne OK", "Écart", "Chute Pression")
        v_turb_cls = get_cls(d.get("turbine_speed", 6435), 6300, 6500)
        v_turb_sub = get_sub(v_turb_cls, "Nominal", "Instable", "Critique")
        pow_cls    = get_cls(d.get("active_power", 24), 0, 32)
        pow_sub    = get_sub(pow_cls, "+0.2% stable", "Fluctuation", "Sous-charge")
        pf_cls     = get_cls(d.get("power_factor", 0.85), 0.80, 0.90)
        pf_sub     = get_sub(pf_cls, "Aucun écart", "Déphasage", "Défaut")
        eff_cls    = get_cls(d.get("efficiency", 92), 80, 100)
        eff_sub    = get_sub(eff_cls, "Optimal", "Dégradé", "mauvais")
        t_hp_cls   = get_cls(d.get("temperature_hp", 470), 440, 500)
        t_hp_sub   = get_sub(t_hp_cls, "Stable", "Proche limite", "Surchauffe")

        return [
            badge(d.get("active_power",   0), "PUISSANCE ACTIVE",    "MW",    pow_cls,    pow_sub[0],    pow_sub[1]),
            badge(d.get("turbine_speed",  0), "VITESSE TURBINE",     "RPM",   v_turb_cls, v_turb_sub[0], v_turb_sub[1]),
            badge(d.get("pressure_hp",    0), "PRESSION HP",         "bar",   p_hp_cls,   p_hp_sub[0],   p_hp_sub[1]),
            badge(d.get("power_factor",   0), "FACTEUR DE PUISSANCE","cos φ", pf_cls,     pf_sub[0],     pf_sub[1]),
            badge(d.get("efficiency",     0), "RENDEMENT",           "%",     eff_cls,    eff_sub[0],    eff_sub[1]),
            badge(d.get("temperature_hp", 0), "TEMP. HP",            "°C",    t_hp_cls,   t_hp_sub[0],   t_hp_sub[1]),
        ]

    # ── Jauges — mise à jour partielle via Patch ──────────────────────
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
        if not d:
            d = {k: cfg["min"] + (cfg["max"] - cfg["min"]) * 0.5
                 for k, cfg in GAUGE_CONFIGS.items()}
        # Reconstruit la figure uniquement si nécessaire (valeurs différentes)
        return [make_gauge(d.get(k, cfg["min"]), cfg) for k, cfg in GAUGE_CONFIGS.items()]

    # ── Graphique temps réel — figure de base + mise à jour incrémentale ──
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
            return _make_empty_rt_figure()

        # Si la figure n'existe pas encore, construire la structure de base
        if current_fig is None:
            return _make_empty_rt_figure()

        # Mise à jour incrémentale : Patch ne modifie que x/y de chaque trace
        patched = Patch()
        ts = d.get("timestamp", "")[:19]

        for i, param in enumerate(_RT_COLORS):
            val = d.get(param, 0)
            if param == "turbine_speed":
                val = val / 100
            patched["data"][i]["x"] = current_fig["data"][i]["x"] + [ts]
            patched["data"][i]["y"] = current_fig["data"][i]["y"] + [val]
            # Garder seulement les 60 derniers points dans le graphique
            if len(patched["data"][i]["x"]) > 60:
                patched["data"][i]["x"] = patched["data"][i]["x"][-60:]
                patched["data"][i]["y"] = patched["data"][i]["y"][-60:]

        return patched

    # ── Alertes ───────────────────────────────────────────────────────
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

    # ── Synoptique GTA ────────────────────────────────────────────────
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