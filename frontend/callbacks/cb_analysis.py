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
from dash import Input, Output, State, html, no_update, ctx, Patch
import pandas as pd
from datetime import datetime, timedelta
from config import BACKEND, TIMEZONE_OFFSET
from components.gauges import make_gauge, get_gauge_color, GAUGE_CONFIGS

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
            "bgcolor": "rgba(0,0,0,0)", "itemclick": "toggleothers", "itemdoubleclick": "toggle"},
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
                "pressure_bp_barillet", "steam_flow_condenser"]


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
        now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
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

    # ── Jauges CRITIQUES (Fast) — live sur push WS ────────────────────
    @app.callback(
        [Output(f"gauge-{k}", "figure") for k in _GAUGES_FAST],
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_gauges_fast(d, pathname):
        if pathname != "/analysis" or not d:
            return [no_update] * len(_GAUGES_FAST)
            
        patches = []
        for k in _GAUGES_FAST:
            v = d.get(k)
            if v is None:
                patches.append(no_update)
            else:
                p = Patch()
                color = get_gauge_color(v, GAUGE_CONFIGS[k])
                p["data"][0]["value"] = v
                p["data"][0]["number"]["font"]["color"] = color
                p["data"][0]["gauge"]["bar"]["color"] = color
                patches.append(p)
        return patches

    # ── Jauges SECONDAIRES (Slow) — live sur push WS ──────────────────
    @app.callback(
        [Output(f"gauge-{k}", "figure") for k in _GAUGES_SLOW],
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_gauges_slow(d, pathname):
        if pathname != "/analysis" or not d:
            return [no_update] * len(_GAUGES_SLOW)
            
        patches = []
        for k in _GAUGES_SLOW:
            v = d.get(k)
            if v is None:
                patches.append(no_update)
            else:
                p = Patch()
                color = get_gauge_color(v, GAUGE_CONFIGS[k])
                p["data"][0]["value"] = v
                p["data"][0]["number"]["font"]["color"] = color
                p["data"][0]["gauge"]["bar"]["color"] = color
                patches.append(p)
        return patches

    # ── KPIs & Analyse combinés ───────────────────────────────────────
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
        Output("history-chart",         "figure"),
        Output("stats-table",           "children"),
        Output("status-pie",            "figure"),
        Output("history-data-table",    "children"),
        Input("btn-refresh-history",    "n_clicks"),
        Input("interval-analysis",      "n_intervals"),
        Input("url",                    "pathname"),
        State("date-start",             "value"),
        State("date-end",               "value"),
        State("param-selector",         "value"),
        prevent_initial_call=False,
    )
    def update_kpis_and_analysis(_, __, pathname, date_start, date_end, params):
        if pathname != "/analysis":
            return [no_update] * 16

        # Build query parameters
        query = ""
        if date_start:
            query += f"&start={date_start}T00:00:00"
        if date_end:
            query += f"&end={date_end}T23:59:59"

        # 1. Fetch statistics (FAST - pre-calculated on backend)
        try:
            stats = _session.get(f"{BACKEND}/data/statistics?{query}", timeout=2).json()
        except Exception:
            stats = {}

        # 2. Fetch history for the chart (OPTIMIZED - limit reduced to 500)
        try:
            history_url = f"{BACKEND}/data/history?limit=500{query}"
            data = _session.get(history_url, timeout=3).json()
        except Exception:
            data = []

        empty_layout = dict(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis={**_DARK_LAYOUT["xaxis"], "showgrid": False, "showticklabels": False},
            yaxis={**_DARK_LAYOUT["yaxis"], "showgrid": False, "showticklabels": False},
            annotations=[{
                "text": "Aucune donnée disponible pour cette période",
                "xref": "paper", "yref": "paper",
                "showarrow": False,
                "font": {"size": 13, "color": "#64748b", "family": "Share Tech Mono"}
            }],
        )
        na = "—"

        if not data:
            empty = go.Figure()
            empty.update_layout(**empty_layout)
            return (
                na, "Pas de données", na, "", na, "", na, "", na, "", na, "",
                empty,
                html.Div("Veuillez sélectionner une autre période", style={"color": "#64748b", "fontFamily": "Share Tech Mono", "padding": "10px"}),
                empty,
                html.Div("Pas de données")
            )

        df = pd.DataFrame(data)
        
        # ── KPIs (Using Backend Stats) ──
        p_stats = stats.get("active_power", {})
        power_avg_txt = f"{p_stats.get('mean', 0):.1f}"
        power_sub_txt = f"Max : {p_stats.get('max', 0):.1f} MW"

        eff_nom = 92.0
        eff_stats = stats.get("efficiency", {})
        eff_avg = eff_stats.get("mean", 0)
        eff_delta = eff_avg - eff_nom
        eff_avg_txt = f"{eff_avg:.1f}"
        eff_sub_txt = f"vs nominal : {'▲' if eff_delta >= 0 else '▼'} {abs(eff_delta):.1f}%"

        spd_stats = stats.get("turbine_speed", {})
        spd_avg_txt = f"{spd_stats.get('mean', 0):.0f}"
        spd_sub_txt = f"σ = {spd_stats.get('std', 0):.0f} RPM"

        try:
            alerts_url = f"{BACKEND}/settings/alerts?limit=500"
            alerts_data = _session.get(alerts_url, timeout=2).json()
            n_alerts = len(alerts_data)
            n_crit   = sum(1 for a in alerts_data if a.get("severity") == "CRITICAL")
        except Exception:
            n_alerts, n_crit = 0, 0
        alerts_txt, alerts_sub_txt = str(n_alerts), f"{n_crit} critique(s)"

        # Tempe dégradé depuis la distribution des statuts (Backend)
        dist = stats.get("status_distribution", {})
        pct_deg = dist.get("DEGRADED", {}).get("pct", 0) + dist.get("CRITICAL", {}).get("pct", 0)
        deg_txt = f"{pct_deg:.1f}"
        deg_sub_txt = "NORMAL" if pct_deg < 5 else ("⚠ Surveiller" if pct_deg < 20 else "🔴 Critique")

        points_txt = str(len(data)) # Note: Using data visible on chart
        if stats:
            # We fetch up to 10k for stats on backend, let's show total if returned
            # Logic: Backend get_statistics fetches limit=10000.
            # We don't have a direct 'total' but we can infer or leave it as is.
            pass

        period_sub = "Toute la base"
        if date_start:
            period_sub = f"Du {date_start}" + (f" au {date_end}" if date_end else "")

        # ── Analysis Components (Using 500-point Downsampled Data) ──
        timestamps = df.get("timestamp", pd.Series(dtype=str)).str[:19]
        fig = go.Figure()
        for p in (params or ["active_power"]):
            if p in df.columns:
                fig.add_trace(go.Scatter(
                    x=timestamps, y=df[p],
                    name=PARAM_LABELS.get(p, p),
                    line={"color": PARAM_COLORS.get(p, "#3b82f6"), "width": 1.5},
                    mode="lines"
                ))
        fig.update_layout(margin={"t": 10, "b": 30, "l": 50, "r": 10}, **_DARK_LAYOUT)

        # ── Statistics Table (Using Backend Stats) ──
        stat_params = ["pressure_hp", "temperature_hp", "active_power", "turbine_speed", "efficiency"]
        rows = [html.Tr([html.Th(h) for h in ["Paramètre", "Moyenne", "Min", "Max", "Écart-type"]], style={"background": "#080c10"})]
        for p in stat_params:
            if p in stats:
                s = stats[p]
                rows.append(html.Tr([
                    html.Td(PARAM_LABELS.get(p, p)),
                    html.Td(f"{s['mean']:.2f}"), html.Td(f"{s['min']:.2f}"),
                    html.Td(f"{s['max']:.2f}"), html.Td(f"{s['std']:.2f}")
                ]))
        stats_table = html.Table(rows, className="data-table")

        # ── Pie Statuts (Using Backend Stats Distribution) ──
        pie_labels = list(dist.keys())
        pie_values = [v["count"] for v in dist.values()]
        pie = go.Figure(go.Pie(
            labels=pie_labels,
            values=pie_values,
            hole=0.6,
            marker={"colors": ["#10b981", "#f59e0b", "#ef4444"]},
            textfont={"family": "Inter, sans-serif", "size": 11, "color": "#f8fafc"},
        ))
        pie.update_layout(
            margin={"t": 10, "b": 10, "l": 10, "r": 10},
            showlegend=True,
            **{k: v for k, v in _DARK_LAYOUT.items() if k not in ("hovermode", "uirevision", "xaxis", "yaxis")},
        )

        last10 = data[:10]
        tbl_hdr = html.Tr([html.Th(h) for h in ["Timestamp", "P-HP (bar)", "T-HP (°C)", "RPM", "P (MW)", "cosφ", "Statut"]])
        tbl_rows = [html.Tr([
            html.Td(d.get("timestamp", "")[:19].replace("T", " ")),
            html.Td(f"{d.get('pressure_hp', 0):.1f}"),
            html.Td(f"{d.get('temperature_hp', 0):.1f}"),
            html.Td(f"{d.get('turbine_speed', 0):.0f}"),
            html.Td(f"{d.get('active_power', 0):.2f}"),
            html.Td(f"{d.get('power_factor', 0):.3f}"),
            html.Td(html.Span(d.get("status", "NORMAL"), className=f"status-pill {d.get('status','NORMAL').lower()}" if isinstance(d.get('status'), str) else "status-pill normal")),
        ]) for d in last10]
        data_table = html.Table([html.Thead(tbl_hdr), html.Tbody(tbl_rows)], className="data-table")

        return (
            power_avg_txt, power_sub_txt, eff_avg_txt, eff_sub_txt,
            spd_avg_txt, spd_sub_txt, alerts_txt, alerts_sub_txt,
            deg_txt, deg_sub_txt, points_txt, period_sub,
            fig, stats_table, pie, data_table
        )