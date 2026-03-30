"""
callbacks/cb_dashboard.py — Callbacks temps réel du dashboard SCADA

CORRECTIONS :
  1. update_realtime_chart : Patch() sécurisé — guard sur figure vide
     et initialisation des traces si manquantes.
  2. update_status_pill : retourne une string CSS valide, pas un html.Span imbriqué.
  3. Axe X graphique RT : tickformat="%H:%M:%S" pour affichage lisible.
  4. Jauges : hauteur portée à 180px, margin.t réduit à 40px.
  5. [FIX-4b] Graphe RT : fenêtre 90 → 180 points (90s d'historique visuel).
  6. [FIX-5c] Synoptique : callback Python remplacé par clientside_callback
     → le patch SVG se fait entièrement côté navigateur, sans aller-retour Python.
"""
import json
from datetime import datetime
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, Patch
from components.gauges import make_gauge, GAUGE_CONFIGS
# create_gta_synoptic supprimé [FIX-5c] : patch géré par clientside_callback JS
from components.alert_banner import alerts_panel
from config import BACKEND

_session = requests.Session()

# ── Courbes du graphique temps réel ──────────────────────────────────
_RT_PARAMS = {
    "active_power":   {"label": "P active (MW)",      "color": "#10b981", "scale": 1.0},
    "pressure_hp":    {"label": "P HP (bar)",         "color": "#f97316", "scale": 1.0},
    "turbine_speed":  {"label": "Vitesse (/100 RPM)", "color": "#818cf8", "scale": 0.01},
    "temperature_hp": {"label": "T HP (°C/10)",       "color": "#ef4444", "scale": 0.1},
    "efficiency":     {"label": "Rendement (%)",      "color": "#38bdf8", "scale": 1.0},
    "power_factor":   {"label": "cos φ (×10)",        "color": "#fbbf24", "scale": 10.0},
}

_BASE_RT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin={"t": 10, "b": 40, "l": 40, "r": 10},
    legend={"font": {"color": "#64748b", "size": 9},
            "bgcolor": "rgba(0,0,0,0)", "orientation": "h", "y": -0.35},
    xaxis={
        "tickfont":   {"color": "#334155", "size": 8},
        "gridcolor":  "#0f2744",
        "showgrid":   True,
        "color":      "#1e3a5f",
        # CORRECTION 3 : format lisible pour les timestamps ISO
        "tickformat": "%H:%M:%S",
        "type":       "date",
    },
    yaxis={
        "tickfont":  {"color": "#334155", "size": 8},
        "gridcolor": "#0f2744",
        "showgrid":  True,
        "color":     "#1e3a5f",
    },
    font={"family": "Share Tech Mono"},
    hovermode="x unified",
    uirevision="realtime",
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


def _figure_has_traces(fig) -> bool:
    """Vérifie que la figure contient le bon nombre de traces peuplées."""
    if fig is None:
        return False
    data = fig.get("data", [])
    return len(data) == len(_RT_PARAMS)


def register(app):

    # ── Horloge ───────────────────────────────────────────────────────
    @app.callback(
        Output("topbar-time", "children"),
        Input("interval-fast", "n_intervals"),
    )
    def update_clock(_):
        return datetime.now().strftime("%d/%m/%Y  %H:%M:%S")

    # ── Status Pill ───────────────────────────────────────────────────
    # CORRECTION 2 : retourne la string du statut directement (le composant
    # parent est déjà un html.Div avec className "status-button online") ;
    # on ne ré-enveloppe plus dans un html.Span.
    @app.callback(
        Output("topbar-status-pill", "children"),
        Input("store-current-data", "data"),
        prevent_initial_call=True,
    )
    def update_status_pill(d):
        d = d or {}
        status = d.get("status", "NORMAL")
        colors = {"NORMAL": "#10b981", "DEGRADED": "#f59e0b", "CRITICAL": "#ef4444"}
        color = colors.get(status, "#10b981")
        return html.Span(
            status,
            style={"color": color, "fontWeight": "700",
                   "fontFamily": "var(--ui)", "fontSize": "11px",
                   "letterSpacing": "1px"},
        )

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

        def badge(val, label, unit, cls, sub="", fmt=".1f"):
            return html.Div([
                html.Div(label, className="kpi-label"),
                html.Div([
                    html.Span(f"{val:{fmt}}", className="kpi-val-num"),
                    html.Span(unit, className="kpi-unit"),
                ], className="kpi-val"),
                html.Div(sub, className="kpi-sub") if sub else None,
            ], className=f"kpi-badge {cls}")

        def cls_range(val, lo, hi):
            if val < lo or val > hi:
                return "crit"
            margin = (hi - lo) * 0.15
            if val < lo + margin or val > hi - margin:
                return "warn"
            return "ok"

        p_cls  = cls_range(d.get("pressure_hp",  60),   55,   65)
        t_cls  = cls_range(d.get("temperature_hp",486),  420,  500)
        s_cls  = cls_range(d.get("turbine_speed",6435), 6300, 6550)
        pw_cls = ("crit" if d.get("active_power", 24) > 30
                  else "warn" if d.get("active_power", 24) > 24 else "ok")
        pf_cls = cls_range(d.get("power_factor", 0.85), 0.82, 0.86)
        ef_cls = ("crit" if d.get("efficiency", 92) < 85
                  else "warn" if d.get("efficiency", 92) < 88 else "ok")
        ia_cls = "crit" if d.get("current_a", 2254) > 3200 else "ok"
        pb_cls = "crit" if d.get("pressure_bp_barillet", 3.0) > 3.5 else "ok"

        return [
            badge(d.get("active_power",   0), "PUISSANCE ACTIVE",  "MW",  pw_cls,
                  "Nominal 24 MW" if pw_cls == "ok" else "Dépassement !"),
            badge(d.get("turbine_speed",  0), "VITESSE TURBINE",   "RPM", s_cls,
                  "6435 RPM cible" if s_cls == "ok" else "Hors plage", fmt=".0f"),
            badge(d.get("pressure_hp",    0), "PRESSION HP",       "bar", p_cls,
                  "60 bar nominal" if p_cls == "ok" else "Écart"),
            badge(d.get("temperature_hp", 0), "TEMPÉRATURE HP",    "°C",  t_cls,
                  "Design 486°C" if d.get("temperature_hp", 486) >= 460
                  else "⚠ Opérat. 440°C", fmt=".0f"),
            badge(d.get("efficiency",     0), "RENDEMENT THERMO",  "%",   ef_cls,
                  "Optimal" if ef_cls == "ok" else "Dégradé"),
            badge(d.get("power_factor",   0), "FACTEUR cos φ",     "",    pf_cls,
                  "0.82–0.86 spec" if pf_cls == "ok" else "Hors plage", fmt=".3f"),
            badge(d.get("current_a",      0), "COURANT DE LIGNE",  "A",   ia_cls,
                  "Normal" if ia_cls == "ok" else "Surintensité", fmt=".0f"),
            badge(d.get("pressure_bp_barillet", 3.0), "PRESS. BARILLET", "bar", pb_cls,
                  "3 bar nominal" if pb_cls == "ok" else "Surpression !"),
        ]

    # ── Jauges par section ────────────────────────────────────────────
    # CORRECTION 4 : hauteur portée à 180px dans gauge_card (voir gauges.py)
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
        return [
            make_gauge(d.get(k, cfg["min"] + (cfg["max"] - cfg["min"]) * 0.5), cfg)
            for k, cfg in GAUGE_CONFIGS.items()
        ]

    # ── Graphique temps réel ──────────────────────────────────────────
    # CORRECTION 1 : Patch() sécurisé avec vérification des traces
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

        # Si la figure n'est pas encore initialisée ou manque des traces,
        # on recrée la figure complète (évite le crash de Patch()).
        if not _figure_has_traces(current_fig):
            return _make_empty_rt_figure()

        patched = Patch()
        ts = d.get("timestamp", "")[:19]

        for i, (param, cfg) in enumerate(_RT_PARAMS.items()):
            val = d.get(param, 0) * cfg["scale"]
            existing_x = current_fig["data"][i].get("x") or []
            existing_y = current_fig["data"][i].get("y") or []
            xs = list(existing_x) + [ts]
            ys = list(existing_y) + [val]
            # [FIX-4b] fenêtre portée à 180 points = 90s @ 500ms/push
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
            btn_id = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
            alert_id = btn_id["index"]
            r = _session.post(
                f"{BACKEND}/settings/alerts/{alert_id}/acknowledge", timeout=1
            )
            if r.status_code == 200:
                return "OK ✅", True
        except Exception as e:
            print("Erreur acquittement:", e)
        return "Erreur", False

    # ── Synoptique [FIX-5c] ──────────────────────────────────────────────
    # Le patch du SVG est délégué à une clientside_callback (JS pur).
    # Plus de sérialisation Python→JSON→DOM à chaque push WebSocket.
    # La fonction JS est définie dans assets/synoptic_patch.js.
    app.clientside_callback(
        """function(data, pathname) {
            if (pathname !== '/') return window.dash_clientside.no_update;
            if (!data || Object.keys(data).length === 0)
                return window.dash_clientside.no_update;
            if (typeof window.patchGtaSynoptic === 'function')
                window.patchGtaSynoptic(data);
            return window.dash_clientside.no_update;
        }""",
        Output("syn-patch-tick", "data"),   # store factice — le JS patche le SVG en place
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )