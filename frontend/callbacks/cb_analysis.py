"""
callbacks/cb_analysis.py — Callbacks page Analyse & Historique

MODIFICATIONS :
  1. toggle_analysis_mode() : bascule analysis-mode entre "live" et "history"
     Déclencheur : clic sur qf-live, qf-1h, qf-6h, qf-24h, qf-7j, qf-all
  2. update_mode_indicator() : met à jour le pill coloré dans le header du graphe
  3. update_chart_live() : graphe LIVE (source = store-history WS, ~2m30s)
     Déclenché uniquement si analysis-mode == "live"
  4. update_kpis_and_analysis() : court-circuité si mode == "live" (chart seulement)
  5. apply_quick_filter() : retourne no_update pour date si mode LIVE activé
  6. highlight_active_filter() : étend la mise en évidence au bouton LIVE
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

_DARK_LAYOUT_LIVE = {
    **_DARK_LAYOUT,
    "uirevision": "analysis-live",   # reset propre quand on bascule en LIVE
    "xaxis": {
        **_DARK_LAYOUT["xaxis"],
        "type": "date",
        "tickformat": "%H:%M:%S",
    },
}

_GAUGES_FAST = ["pressure_hp", "temperature_hp", "active_power",
                "turbine_speed", "efficiency"]
_GAUGES_SLOW = ["reactive_power", "apparent_power", "power_factor",
                "current_a", "voltage",
                "steam_flow_hp", "pressure_bp_in",
                "pressure_bp_barillet", "steam_flow_condenser"]

_ALL_FILTER_IDS = ["qf-live", "qf-1h", "qf-6h", "qf-24h", "qf-7j", "qf-all"]

# Liste maître des options du sélecteur de paramètres (option = clé colonne)
_ALL_PARAM_OPTIONS = [
    {"label": "Pression HP (bar)",     "value": "pressure_hp"},
    {"label": "Température HP (°C)",   "value": "temperature_hp"},
    {"label": "Vitesse turbine (RPM)", "value": "turbine_speed"},
    {"label": "Puissance active (MW)", "value": "active_power"},
    {"label": "Facteur cosφ",          "value": "power_factor"},
    {"label": "Rendement (%)",         "value": "efficiency"},
    {"label": "Débit vapeur HP (T/h)", "value": "steam_flow_hp"},
]


def register(app):

    # ══════════════════════════════════════════════════════════════════
    # Sélecteur mono-paramètre (vue graphe) — options dérivées du filtre
    # ══════════════════════════════════════════════════════════════════
    @app.callback(
        Output("param-view", "options"),
        Output("param-view", "value"),
        Input("param-selector", "value"),
        State("param-view", "value"),
    )
    def update_param_view(selected, current):
        """Filtre vide → toutes les options ; sinon restreint à la sélection.
        Conserve la valeur courante si encore valide, sinon prend la 1re."""
        if not selected:
            opts = _ALL_PARAM_OPTIONS
        else:
            opts = [o for o in _ALL_PARAM_OPTIONS if o["value"] in selected]
        valid = {o["value"] for o in opts}
        if current in valid:
            return opts, current
        return opts, (opts[0]["value"] if opts else None)

    # ══════════════════════════════════════════════════════════════════
    # URL CSV dynamique (respecte la sélection + plage)
    # ══════════════════════════════════════════════════════════════════
    @app.callback(
        Output("btn-export-csv", "href"),
        Input("param-selector", "value"),
        Input("date-start",     "value"),
        Input("date-end",       "value"),
    )
    def update_csv_url(params, date_start, date_end):
        qs = []
        if date_start:
            qs.append(f"start={date_start}T00:00:00")
        if date_end:
            qs.append(f"end={date_end}T23:59:59")
        if params:
            qs.extend(f"params={p}" for p in params)
        base = f"{BACKEND}/data/export/csv"
        return f"{base}?{'&'.join(qs)}" if qs else base

    # ══════════════════════════════════════════════════════════════════
    # ÉTAPE 1 — Bascule du mode analysis (LIVE ↔ HISTORY)
    # ══════════════════════════════════════════════════════════════════

    @app.callback(
        Output("analysis-mode", "data"),
        [Input(fid, "n_clicks") for fid in _ALL_FILTER_IDS],
        prevent_initial_call=True,
    )
    def toggle_analysis_mode(*_):
        triggered = ctx.triggered_id
        if triggered == "qf-live":
            return "live"
        # N'importe quel autre bouton période → retour en mode history
        if triggered in ("qf-1h", "qf-6h", "qf-24h", "qf-7j", "qf-all"):
            return "history"
        return no_update

    # ── Indicateur de mode (pill dans le header du graphe) ───────────
    @app.callback(
        Output("analysis-mode-indicator", "children"),
        Input("analysis-mode", "data"),
    )
    def update_mode_indicator(mode):
        if mode == "live":
            return [
                html.Span("●", style={
                    "color": "#10b981", "marginRight": "5px",
                    "fontSize": "10px", "animation": "blink 1.2s step-end infinite",
                }),
                html.Span("LIVE — temps réel 2m30s", style={
                    "color": "#10b981", "fontSize": "10px",
                    "fontFamily": "Share Tech Mono", "fontWeight": "700",
                    "letterSpacing": "1px",
                }),
            ]
        return [
            html.Span("●", style={
                "color": "#334155", "marginRight": "5px", "fontSize": "10px",
            }),
            html.Span("HISTORIQUE", style={
                "color": "#334155", "fontSize": "10px",
                "fontFamily": "Share Tech Mono", "letterSpacing": "1px",
            }),
        ]

    # ── Mise en évidence du bouton actif (inclut LIVE) ───────────────
    @app.callback(
        [Output(fid, "className") for fid in _ALL_FILTER_IDS],
        Input("analysis-mode",   "data"),
        [Input(fid, "n_clicks") for fid in _ALL_FILTER_IDS],
        prevent_initial_call=True,
    )
    def highlight_active_filter(mode, *_):
        triggered = ctx.triggered_id
        classes = []
        for fid in _ALL_FILTER_IDS:
            if fid == "qf-live":
                # LIVE actif si mode == "live"
                cls = "btn btn-success" if mode == "live" else "btn btn-outline"
                classes.append(cls)
            else:
                cls = "btn btn-primary" if fid == triggered and mode == "history" else "btn btn-outline"
                classes.append(cls)
        return classes

    # ── Filtres rapides → dates (désactivés en mode LIVE) ────────────
    @app.callback(
        Output("date-start", "value"),
        Output("date-end",   "value"),
        [Input(fid, "n_clicks") for fid in _ALL_FILTER_IDS],
        prevent_initial_call=True,
    )
    def apply_quick_filter(*_):
        triggered = ctx.triggered_id
        # En mode LIVE : pas de filtre date
        if triggered == "qf-live":
            return no_update, no_update

        now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
        end_str = now.strftime("%Y-%m-%d")
        mapping = {
            "qf-1h":  timedelta(hours=1),
            "qf-6h":  timedelta(hours=6),
            "qf-24h": timedelta(hours=24),
            "qf-7j":  timedelta(days=7),
        }
        if triggered == "qf-all":
            return None, end_str
        delta = mapping.get(triggered)
        if delta:
            return (now - delta).strftime("%Y-%m-%d"), end_str
        return no_update, no_update

    # ══════════════════════════════════════════════════════════════════
    # ÉTAPE 1 — Graphe LIVE (source = store-history WS)
    # Séparé du graphe historique pour éviter les conflits de callback.
    # ══════════════════════════════════════════════════════════════════

    @app.callback(
        Output("history-chart", "figure", allow_duplicate=True),
        Input("store-history",  "data"),          # mis à jour à chaque push WS
        Input("param-view",     "value"),         # changement de paramètre vue
        State("analysis-mode",  "data"),
        State("url",            "pathname"),
        prevent_initial_call=True,
    )
    def update_chart_live(history, param, mode, pathname):
        """
        Graphe LIVE mono-paramètre : affiché quand analysis-mode == 'live'.
        Source : store-history (derniers 300 snapshots WS, ~2m30s @500ms/push).
        """
        if pathname != "/analysis" or mode != "live":
            return no_update
        if not history:
            fig = go.Figure()
            fig.update_layout(
                **_DARK_LAYOUT_LIVE,
                margin={"t": 10, "b": 30, "l": 50, "r": 10},
                annotations=[{
                    "text": "En attente de données WebSocket...",
                    "xref": "paper", "yref": "paper", "showarrow": False,
                    "font": {"size": 12, "color": "#334155", "family": "Share Tech Mono"},
                }],
            )
            return fig

        param = param or "active_power"
        fig   = go.Figure()
        xs, ys = [], []
        for pt in history:
            ts = pt.get("timestamp", "")
            v  = pt.get(param)
            if ts and v is not None:
                xs.append(ts[:19])
                ys.append(v)
        if xs:
            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                name=PARAM_LABELS.get(param, param),
                line={"color": PARAM_COLORS.get(param, "#3b82f6"), "width": 1.5},
                mode="lines",
            ))

        fig.update_layout(
            margin={"t": 10, "b": 30, "l": 50, "r": 10},
            **_DARK_LAYOUT_LIVE,
        )
        return fig

    # ══════════════════════════════════════════════════════════════════
    # Jauges CRITIQUES (Fast) — live sur push WS
    # ══════════════════════════════════════════════════════════════════

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

    # ── Jauges SECONDAIRES (Slow) ────────────────────────────────────
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

    # ══════════════════════════════════════════════════════════════════
    # KPIs & Analyse HISTORIQUE
    # Court-circuité si mode == "live" pour ne pas écraser le graphe live.
    # ══════════════════════════════════════════════════════════════════

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
        Input("param-view",             "value"),       # change de param vue
        State("analysis-mode",          "data"),        # ← NOUVEAU
        State("date-start",             "value"),
        State("date-end",               "value"),
        prevent_initial_call=False,
    )
    def update_kpis_and_analysis(_, __, pathname, param, mode, date_start, date_end):
        if pathname != "/analysis":
            return [no_update] * 16

        # ── COURT-CIRCUIT MODE LIVE ──────────────────────────────────
        # En mode live, le graphe est géré par update_chart_live().
        # On laisse les KPIs et stats se mettre à jour (ils sont toujours utiles),
        # mais on ne touche pas au graphe (history-chart → no_update).
        skip_chart = (mode == "live")

        query = ""
        if date_start:
            query += f"&start={date_start}T00:00:00"
        if date_end:
            query += f"&end={date_end}T23:59:59"

        try:
            stats = _session.get(f"{BACKEND}/data/statistics?{query}", timeout=2).json()
        except Exception:
            stats = {}

        try:
            data = _session.get(f"{BACKEND}/data/history?limit=500{query}", timeout=3).json()
        except Exception:
            data = []

        empty_layout = dict(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis={**_DARK_LAYOUT["xaxis"], "showgrid": False, "showticklabels": False},
            yaxis={**_DARK_LAYOUT["yaxis"], "showgrid": False, "showticklabels": False},
            annotations=[{
                "text": "Aucune donnée disponible pour cette période",
                "xref": "paper", "yref": "paper", "showarrow": False,
                "font": {"size": 13, "color": "#64748b", "family": "Share Tech Mono"},
            }],
        )
        na = "—"

        if not data:
            empty = go.Figure()
            empty.update_layout(**empty_layout)
            chart_out = no_update if skip_chart else empty
            return (
                na, "Pas de données", na, "", na, "", na, "", na, "", na, "",
                chart_out,
                html.Div("Veuillez sélectionner une autre période",
                         style={"color": "#64748b", "fontFamily": "Share Tech Mono", "padding": "10px"}),
                empty,
                html.Div("Pas de données"),
            )

        df = pd.DataFrame(data)

        # ── KPIs ────────────────────────────────────────────────────
        p_stats      = stats.get("active_power", {})
        power_avg    = f"{p_stats.get('mean', 0):.1f}"
        power_sub    = f"Max : {p_stats.get('max', 0):.1f} MW"

        eff_stats = stats.get("efficiency", {})
        eff_avg   = eff_stats.get("mean", 0)
        eff_delta = eff_avg - 92.0
        eff_txt   = f"{eff_avg:.1f}"
        eff_sub   = f"vs nominal : {'▲' if eff_delta >= 0 else '▼'} {abs(eff_delta):.1f}%"

        spd_stats = stats.get("turbine_speed", {})
        spd_txt   = f"{spd_stats.get('mean', 0):.0f}"
        spd_sub   = f"σ = {spd_stats.get('std', 0):.0f} RPM"

        try:
            alerts_data = _session.get(f"{BACKEND}/settings/alerts?limit=500", timeout=2).json()
            n_alerts    = len(alerts_data)
            n_crit      = sum(1 for a in alerts_data if a.get("severity") == "CRITICAL")
        except Exception:
            n_alerts, n_crit = 0, 0

        dist    = stats.get("status_distribution", {})
        pct_deg = dist.get("DEGRADED", {}).get("pct", 0) + dist.get("CRITICAL", {}).get("pct", 0)
        deg_sub = "NORMAL" if pct_deg < 5 else ("⚠ Surveiller" if pct_deg < 20 else "🔴 Critique")
        period_sub = "Toute la base"
        if date_start:
            period_sub = f"Du {date_start}" + (f" au {date_end}" if date_end else "")

        # ── Graphe mono-paramètre (ignoré en mode live) ──────────────
        if skip_chart:
            chart_out = no_update
        else:
            timestamps = df.get("timestamp", pd.Series(dtype=str)).str[:19]
            fig = go.Figure()
            p = param or "active_power"
            if p in df.columns:
                fig.add_trace(go.Scatter(
                    x=timestamps, y=df[p],
                    name=PARAM_LABELS.get(p, p),
                    line={"color": PARAM_COLORS.get(p, "#3b82f6"), "width": 1.5},
                    mode="lines",
                ))
            fig.update_layout(margin={"t": 10, "b": 30, "l": 50, "r": 10}, **_DARK_LAYOUT)
            chart_out = fig

        # ── Tableau stats ────────────────────────────────────────────
        stat_params = ["pressure_hp", "temperature_hp", "active_power", "turbine_speed", "efficiency"]
        rows = [html.Tr([html.Th(h) for h in ["Paramètre", "Moyenne", "Min", "Max", "Écart-type"]],
                        style={"background": "#080c10"})]
        for p in stat_params:
            if p in stats:
                s = stats[p]
                rows.append(html.Tr([
                    html.Td(PARAM_LABELS.get(p, p)),
                    html.Td(f"{s['mean']:.2f}"), html.Td(f"{s['min']:.2f}"),
                    html.Td(f"{s['max']:.2f}"), html.Td(f"{s['std']:.2f}"),
                ]))
        stats_table = html.Table(rows, className="data-table")

        # ── Pie statuts ───────────────────────────────────────────────
        pie_labels = list(dist.keys())
        pie_values = [v["count"] for v in dist.values()]
        pie = go.Figure(go.Pie(
            labels=pie_labels, values=pie_values, hole=0.6,
            marker={"colors": ["#10b981", "#f59e0b", "#ef4444"]},
            textfont={"family": "Inter, sans-serif", "size": 11, "color": "#f8fafc"},
        ))
        pie.update_layout(
            margin={"t": 10, "b": 10, "l": 10, "r": 10}, showlegend=True,
            **{k: v for k, v in _DARK_LAYOUT.items()
               if k not in ("hovermode", "uirevision", "xaxis", "yaxis")},
        )

        # ── Tableau dernières entrées ─────────────────────────────────
        last10  = data[:10]
        tbl_hdr = html.Tr([html.Th(h) for h in
                           ["Timestamp", "P-HP (bar)", "T-HP (°C)", "RPM", "P (MW)", "cosφ", "Statut"]])
        tbl_rows = [html.Tr([
            html.Td(d.get("timestamp", "")[:19].replace("T", " ")),
            html.Td(f"{d.get('pressure_hp', 0):.1f}"),
            html.Td(f"{d.get('temperature_hp', 0):.1f}"),
            html.Td(f"{d.get('turbine_speed', 0):.0f}"),
            html.Td(f"{d.get('active_power', 0):.2f}"),
            html.Td(f"{d.get('power_factor', 0):.3f}"),
            html.Td(html.Span(
                d.get("status", "NORMAL"),
                className=f"status-pill {d.get('status','NORMAL').lower()}"
                          if isinstance(d.get("status"), str) else "status-pill normal",
            )),
        ]) for d in last10]
        data_table = html.Table([html.Thead(tbl_hdr), html.Tbody(tbl_rows)],
                                className="data-table")

        return (
            power_avg, power_sub, eff_txt, eff_sub,
            spd_txt, spd_sub, str(n_alerts), f"{n_crit} critique(s)",
            f"{pct_deg:.1f}", deg_sub, str(len(data)), period_sub,
            chart_out, stats_table, pie, data_table,
        )