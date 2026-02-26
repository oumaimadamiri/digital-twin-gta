"""
callbacks/cb_analysis.py — Callbacks page Analyse & Historique
Optimisé :
  - Session HTTP réutilisable
  - prevent_initial_call=True
  - Intervalles rallongés (30s par défaut, rafraîchi uniquement si page active)
  - Calcul des stats via pandas vectorisé au lieu de boucles Python
"""
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update
import pandas as pd
from config import BACKEND

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

# Layout de base partagé pour les figures d'analyse
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


def register(app):

    @app.callback(
        Output("history-chart", "figure"),
        Output("stats-table", "children"),
        Output("status-pie", "figure"),
        Output("history-data-table", "children"),
        Input("btn-refresh-history", "n_clicks"),
        Input("interval-analysis", "n_intervals"),
        State("param-selector", "value"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_analysis(_, __, params, pathname):
        if pathname != "/analysis":
            return [no_update] * 4

        try:
            r    = _session.get(f"{BACKEND}/data/history?limit=200", timeout=3)
            data = r.json()
        except Exception:
            data = []

        empty_layout = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        if not data:
            empty = go.Figure()
            empty.update_layout(**empty_layout)
            return empty, html.Div("Pas de données"), empty, html.Div("Pas de données")

        # ── DataFrame pour traitement vectorisé ──────────────────────
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

        # ── Statistiques vectorisées via pandas ───────────────────────
        stat_params = ["pressure_hp", "temperature_hp", "active_power", "turbine_speed", "efficiency"]
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
            **{k: v for k, v in _DARK_LAYOUT.items() if k not in ("hovermode", "uirevision", "xaxis", "yaxis")},
        )

        # ── Tableau données ───────────────────────────────────────────
        last10 = data[:10]
        tbl_hdr = html.Tr([html.Th(h) for h in
                           ["Timestamp", "P-HP (bar)", "T-HP (°C)", "RPM", "P (MW)", "cosφ", "Statut"]])
        tbl_rows = [html.Tr([
            html.Td(d.get("timestamp", "")[:19].replace("T", " ")),
            html.Td(f"{d.get('pressure_hp', 0):.1f}"),
            html.Td(f"{d.get('temperature_hp', 0):.1f}"),
            html.Td(f"{d.get('turbine_speed', 0):.0f}"),
            html.Td(f"{d.get('active_power', 0):.2f}"),
            html.Td(f"{d.get('power_factor', 0):.3f}"),
            html.Td(html.Span(d.get("status", "NORMAL"),
                              className=f"status-pill {d.get('status', 'NORMAL').lower()}")),
        ]) for d in last10]

        data_table = html.Table([html.Thead(tbl_hdr), html.Tbody(tbl_rows)],
                                className="data-table")
        return fig, stats_table, pie, data_table