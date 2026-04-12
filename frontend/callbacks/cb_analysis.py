"""
callbacks/cb_analysis.py — Callbacks page Analyse & Historique

Ajouts :
  1. Callback update_kpis : calcule les 6 KPIs résumant la période filtrée.
     - Puissance moy / max
     - Rendement moyen vs nominal (92%)
     - Vitesse moyenne
     - Nombre d'alertes (seuil + IA)
     - % temps en état DEGRADED ou CRITICAL
     - Nombre de points enregistrés
  2. Callbacks jauges (fast/slow) déplacés ici depuis cb_dashboard
     avec guard pathname="/analysis".
  3. Filtres rapides (1h, 6h, 24h, 7j, Tout) → remplissent date-start/date-end.
  4. Mise en évidence du bouton filtre actif.
"""
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, ctx
import pandas as pd
from datetime import datetime, timedelta
from config import BACKEND
from components.gauges import make_gauge, GAUGE_CONFIGS

_session = requests.Session()

PARAM_COLORS = {
    "pressure_hp":    "#00b4ff",
    "temperature_hp": "#ff7043",
    "turbine_speed":  "#aa80ff",
    "active_power":   "#00e676",
    "power_factor":   "#ffd740",
    "efficiency":     "#00e5ff",
    "steam_flow_hp":  "#ff80ab",
}

PARAM_LABELS = {
    "pressure_hp":    "Pression HP (bar)",
    "temperature_hp": "Température HP (°C)",
    "turbine_speed":  "Vitesse (RPM)",
    "active_power":   "Puissance (MW)",
    "power_factor":   "cosφ",
    "efficiency":     "Rendement (%)",
    "steam_flow_hp":  "Débit HP (T/h)",
}

_DARK_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    legend={"font": {"family": "Inter, sans-serif", "color": "#94a3b8", "size": 10},
            "bgcolor": "rgba(0,0,0,0)"},
    xaxis={"tickfont": {"family": "Share Tech Mono, monospace", "color": "#64748b", "size": 9},
           "gridcolor": "#1e293b", "color": "#334155"},
    yaxis={"tickfont": {"family": "Share Tech Mono, monospace", "color": "#64748b", "size": 9},
           "gridcolor": "#1e293b", "color": "#334155"},
    hovermode="x unified",
    uirevision="analysis",
)

# Jauges critiques (live, mises à jour sur WS via store-current-data)
_GAUGES_FAST = ["pressure_hp", "temperature_hp", "active_power",
                "turbine_speed", "efficiency"]

# Jauges secondaires (5s)
_GAUGES_SLOW = ["reactive_power", "apparent_power", "power_factor",
                "current_a", "voltage",
                "steam_flow_hp", "pressure_bp_in",
                "pressure_bp_barillet", "pressure_mp_barillet", "steam_flow_condenser"]


def register(app):

    # ── Filtres rapides → remplissent les inputs date ─────────────────
    @app.callback(
        Output("date-start", "value"),
        Output("date-end",   "value"),
        Input("qf-1h",  "n_clicks"),
        Input("qf-6h",  "n_clicks"),
        Input("qf-24h", "n_clicks"),
        Input("qf-7j",  "n_clicks"),
        Input("qf-all", "n_clicks"),
        prevent_initial_call=True,
    )
    def apply_quick_filter(*_):
        now = datetime.utcnow()
        end_str = now.strftime("%Y-%m-%d")
        mapping = {
            "qf-1h":  timedelta(hours=1),
            "qf-6h":  timedelta(hours=6),
            "qf-24h": timedelta(hours=24),
            "qf-7j":  timedelta(days=7),
        }
        triggered = ctx.triggered_id
        if triggered == "qf-all":
            return None, end_str
        delta = mapping.get(triggered)
        if delta:
            return (now - delta).strftime("%Y-%m-%d"), end_str
        return no_update, no_update

    # ── Mise en valeur du bouton actif ────────────────────────────────
    @app.callback(
        Output("qf-1h",  "className"),
        Output("qf-6h",  "className"),
        Output("qf-24h", "className"),
        Output("qf-7j",  "className"),
        Output("qf-all", "className"),
        Input("qf-1h",  "n_clicks"),
        Input("qf-6h",  "n_clicks"),
        Input("qf-24h", "n_clicks"),
        Input("qf-7j",  "n_clicks"),
        Input("qf-all", "n_clicks"),
        prevent_initial_call=True,
    )
    def highlight_active_filter(*_):
        triggered = ctx.triggered_id
        order = ["qf-1h", "qf-6h", "qf-24h", "qf-7j", "qf-all"]
        return [
            "btn btn-primary" if btn_id == triggered else "btn btn-outline"
            for btn_id in order
        ]

    # ── KPIs période ──────────────────────────────────────────────────
    @app.callback(
        Output("kpi-power-avg-val",     "children"),
        Output("kpi-power-max-sub",     "children"),
        Output("kpi-eff-avg-val",       "children"),
        Output("kpi-eff-vs-nom-sub",    "children"),
        Output("kpi-speed-avg-val",     "children"),
        Output("kpi-speed-sub",         "children"),
        Output("kpi-alerts-cnt-val",    "children"),
        Output("kpi-alerts-crit-sub",   "children"),
        Output("kpi-degraded-val",      "children"),
        Output("kpi-degraded-sub",      "children"),
        Output("kpi-points-val",        "children"),
        Output("kpi-period-sub",        "children"),
        Input("btn-refresh-history",    "n_clicks"),
        Input("interval-analysis",      "n_intervals"),
        Input("url",                    "pathname"),
        State("date-start",             "value"),
        State("date-end",               "value"),
        prevent_initial_call=False,
    )
    def update_kpis(_, __, pathname, date_start, date_end):
        if pathname != "/analysis":
            return [no_update] * 12

        # Récupération historique
        url = f"{BACKEND}/data/history?limit=2000"
        if date_start:
            url += f"&start={date_start}T00:00:00"
        if date_end:
            url += f"&end={date_end}T23:59:59"

        try:
            data = _session.get(url, timeout=3).json()
        except Exception:
            data = []

        if not data:
            na = "—"
            return (na, "Pas de données", na, "", na, "", na, "", na, "", na, "")

        df = pd.DataFrame(data)

        # ── Puissance ──
        p_avg = df["active_power"].mean() if "active_power" in df.columns else 0
        p_max = df["active_power"].max()  if "active_power" in df.columns else 0
        power_avg_txt = f"{p_avg:.1f}"
        power_sub_txt = f"Max : {p_max:.1f} MW"

        # ── Rendement ──
        eff_nom = 92.0
        eff_avg = df["efficiency"].mean() if "efficiency" in df.columns else 0
        eff_delta = eff_avg - eff_nom
        eff_avg_txt = f"{eff_avg:.1f}"
        eff_sub_txt = f"vs nominal : {'▲' if eff_delta >= 0 else '▼'} {abs(eff_delta):.1f}%"

        # ── Vitesse ──
        spd_avg = df["turbine_speed"].mean() if "turbine_speed" in df.columns else 0
        spd_std = df["turbine_speed"].std()  if "turbine_speed" in df.columns else 0
        spd_avg_txt = f"{spd_avg:.0f}"
        spd_sub_txt = f"σ = {spd_std:.0f} RPM"

        # ── Alertes (depuis l'API settings) ──
        try:
            alerts_url = f"{BACKEND}/settings/alerts?limit=500"
            alerts_data = _session.get(alerts_url, timeout=2).json()
            n_alerts = len(alerts_data)
            n_crit   = sum(1 for a in alerts_data if a.get("severity") == "CRITICAL")
        except Exception:
            n_alerts, n_crit = 0, 0
        alerts_txt     = str(n_alerts)
        alerts_sub_txt = f"{n_crit} critique(s)"

        # ── Temps dégradé ──
        n_total = len(df)
        if "status" in df.columns and n_total > 0:
            n_deg = df["status"].isin(["DEGRADED", "CRITICAL"]).sum()
            pct_deg = n_deg / n_total * 100
        else:
            pct_deg = 0.0
        deg_txt     = f"{pct_deg:.1f}"
        deg_sub_txt = "NORMAL" if pct_deg < 5 else ("⚠ Surveiller" if pct_deg < 20 else "🔴 Critique")

        # ── Points ──
        points_txt = str(n_total)
        if date_start:
            period_sub = f"Du {date_start}"
            if date_end:
                period_sub += f" au {date_end}"
        else:
            period_sub = "Toute la base"

        return (
            power_avg_txt, power_sub_txt,
            eff_avg_txt,   eff_sub_txt,
            spd_avg_txt,   spd_sub_txt,
            alerts_txt,    alerts_sub_txt,
            deg_txt,       deg_sub_txt,
            points_txt,    period_sub,
        )

    # ── Jauges CRITIQUES (Fast) — live sur push WS ────────────────────
    @app.callback(
        [Output(f"gauge-{k}", "figure") for k in _GAUGES_FAST],
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=False,
    )
    def update_gauges_fast(d, pathname):
        if pathname != "/analysis":
            return [no_update] * len(_GAUGES_FAST)
        d = d or {}
        return [
            make_gauge(d.get(k, GAUGE_CONFIGS[k]["min"] +
                             (GAUGE_CONFIGS[k]["max"] - GAUGE_CONFIGS[k]["min"]) * 0.5),
                       GAUGE_CONFIGS[k])
            for k in _GAUGES_FAST
        ]

    # ── Jauges SECONDAIRES (Slow) — live sur push WS ──────────────────
    @app.callback(
        [Output(f"gauge-{k}", "figure") for k in _GAUGES_SLOW],
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=False,
    )
    def update_gauges_slow(d, pathname):
        if pathname != "/analysis":
            return [no_update] * len(_GAUGES_SLOW)
        d = d or {}
        return [
            make_gauge(d.get(k, GAUGE_CONFIGS[k]["min"] +
                             (GAUGE_CONFIGS[k]["max"] - GAUGE_CONFIGS[k]["min"]) * 0.5),
                       GAUGE_CONFIGS[k])
            for k in _GAUGES_SLOW
        ]

    # ── Graphique + statistiques + tableaux ───────────────────────────
    @app.callback(
        Output("history-chart",      "figure"),
        Output("stats-table",        "children"),
        Output("status-pie",         "figure"),
        Output("history-data-table", "children"),
        Input("btn-refresh-history", "n_clicks"),
        Input("interval-analysis",   "n_intervals"),
        Input("url",                 "pathname"),
        State("date-start",          "value"),
        State("date-end",            "value"),
        State("param-selector",      "value"),
    )
    def update_analysis(_, __, pathname, date_start, date_end, params):
        if pathname != "/analysis":
            return [no_update] * 4

        url = f"{BACKEND}/data/history?limit=500"
        if date_start:
            url += f"&start={date_start}T00:00:00"
        if date_end:
            url += f"&end={date_end}T23:59:59"

        try:
            data = _session.get(url, timeout=3).json()
        except Exception:
            data = []

        empty_layout = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        if not data:
            empty = go.Figure()
            empty.update_layout(**empty_layout)
            return (empty,
                    html.Div("Pas de données pour cette période",
                             style={"color": "#64748b", "fontFamily": "Share Tech Mono",
                                    "padding": "10px"}),
                    empty,
                    html.Div("Pas de données"))

        df = pd.DataFrame(data)
        timestamps = df.get("timestamp", pd.Series(dtype=str)).str[:19]

        # ── Graphique historique ──────────────────────────────────────
        fig = go.Figure()
        for p in (params or ["active_power"]):
            if p in df.columns:
                fig.add_trace(go.Scatter(
                    x=timestamps, y=df[p],
                    name=PARAM_LABELS.get(p, p),
                    line={"color": PARAM_COLORS.get(p, "#3b82f6"), "width": 1.5},
                    mode="lines",
                ))
        fig.update_layout(margin={"t": 10, "b": 30, "l": 50, "r": 10}, **_DARK_LAYOUT)

        # ── Statistiques ──────────────────────────────────────────────
        stat_params = ["pressure_hp", "temperature_hp", "active_power",
                       "turbine_speed", "efficiency"]
        rows = [html.Tr([
            html.Th(h) for h in ["Paramètre", "Moyenne", "Min", "Max", "Écart-type"]
        ], style={"background": "#080c10"})]

        for p in stat_params:
            if p not in df.columns:
                continue
            col = df[p].dropna()
            if col.empty:
                continue
            rows.append(html.Tr([
                html.Td(PARAM_LABELS.get(p, p)),
                html.Td(f"{col.mean():.2f}"),
                html.Td(f"{col.min():.2f}"),
                html.Td(f"{col.max():.2f}"),
                html.Td(f"{col.std():.2f}"),
            ]))
        stats_table = html.Table(rows, className="data-table")

        # ── Pie statuts ───────────────────────────────────────────────
        counts = df["status"].value_counts() if "status" in df.columns else pd.Series()
        pie = go.Figure(go.Pie(
            labels=counts.index.tolist(),
            values=counts.values.tolist(),
            hole=0.6,
            marker={"colors": ["#10b981", "#f59e0b", "#ef4444"][:len(counts)]},
            textfont={"family": "Inter, sans-serif", "size": 11, "color": "#f8fafc"},
        ))
        pie.update_layout(
            margin={"t": 10, "b": 10, "l": 10, "r": 10},
            showlegend=True,
            **{k: v for k, v in _DARK_LAYOUT.items()
               if k not in ("hovermode", "uirevision", "xaxis", "yaxis")},
        )

        # ── Tableau données ───────────────────────────────────────────
        last10 = data[:10]
        tbl_hdr = html.Tr([html.Th(h) for h in
                           ["Timestamp", "P-HP (bar)", "T-HP (°C)", "RPM",
                            "P (MW)", "cosφ", "Statut"]])
        tbl_rows = [html.Tr([
            html.Td(d.get("timestamp", "")[:19].replace("T", " ")),
            html.Td(f"{d.get('pressure_hp', 0):.1f}"),
            html.Td(f"{d.get('temperature_hp', 0):.1f}"),
            html.Td(f"{d.get('turbine_speed', 0):.0f}"),
            html.Td(f"{d.get('active_power', 0):.2f}"),
            html.Td(f"{d.get('power_factor', 0):.3f}"),
            html.Td(html.Span(d.get("status", "NORMAL"),
                              className=f"status-pill {d.get('status','NORMAL').lower()}")),
        ]) for d in last10]

        data_table = html.Table(
            [html.Thead(tbl_hdr), html.Tbody(tbl_rows)],
            className="data-table",
        )
        return fig, stats_table, pie, data_table