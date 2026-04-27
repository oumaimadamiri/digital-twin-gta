"""
callbacks/cb_dashboard.py — Callbacks Dashboard

MODIFICATIONS :
  1. Suppression de update_realtime_chart (graphe 300px → remplacé par sparkline)
  2. Ajout _SPARK_PARAMS : 6 paramètres sélectionnables pour le mini-sparkline
  3. make_empty_spark_figure() : figure initiale du sparkline
  4. select_spark_param() : met à jour store-spark-param via boutons OU clic SVG
  5. update_spark_btn_styles() : met en évidence le bouton actif
  6. update_sparkline() : trace le graphe du paramètre sélectionné (source = store-history)
  7. toggle_spark_poll() : active interval-spark-poll uniquement sur /
  8. poll_svg_click() : clientside callback — lit window._svgClickParam toutes les 300ms
"""
import json
from datetime import datetime
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, Patch, ctx, callback_context as ctx_cb
from components.alert_banner import alerts_panel
from config import BACKEND

_session = requests.Session()

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB + alpha (0..1) → rgba(r,g,b,a) — compatible Plotly."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

# ── Paramètres disponibles pour le mini-sparkline ────────────────────────────
_SPARK_PARAMS = {
    # Plages Y fixes calées sur NOMINAL + THRESHOLDS de backend/core/config.py
    "active_power":   {"label": "P active",  "unit": "MW",  "color": "#10b981", "y_range": [0,    35]},
    "pressure_hp":    {"label": "P HP",      "unit": "bar", "color": "#f97316", "y_range": [45,   75]},
    "steam_flow_hp":  {"label": "Débit HP",  "unit": "T/h", "color": "#06b6d4", "y_range": [60,  160]},
    "turbine_speed":  {"label": "Vitesse",   "unit": "RPM", "color": "#818cf8", "y_range": [5800, 7000]},
    "temperature_hp": {"label": "T HP",      "unit": "°C",  "color": "#ef4444", "y_range": [350,  550]},
    "efficiency":     {"label": "Rendement", "unit": "%",   "color": "#38bdf8", "y_range": [50,  100]},
    "power_factor":   {"label": "cosφ",      "unit": "",    "color": "#fbbf24", "y_range": [0.70, 1.00]},
}

_SPARK_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin={"t": 10, "b": 30, "l": 52, "r": 8},
    xaxis={
        "tickfont":  {"color": "#94a3b8", "size": 9, "family": "Share Tech Mono"},
        "gridcolor": "#1e3a5f", "showgrid": True,
        "color": "#64748b", "tickformat": "%H:%M:%S", "type": "date",
    },
    yaxis={
        "tickfont":  {"color": "#94a3b8", "size": 9, "family": "Share Tech Mono"},
        "gridcolor": "#1e3a5f", "showgrid": True, "color": "#64748b",
    },
    font={"family": "Share Tech Mono"},
    showlegend=False,
    hovermode="x",
)


def make_empty_spark_figure(param: str = "active_power") -> go.Figure:
    """Figure initiale du sparkline avec échelle fixe."""
    cfg = _SPARK_PARAMS.get(param, _SPARK_PARAMS["active_power"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[], y=[],
        mode="lines",
        line={"color": cfg["color"], "width": 2.0},
    ))
    fig.update_layout(**_SPARK_LAYOUT_BASE, uirevision=param)
    fig.update_yaxes(range=cfg["y_range"])
    return fig


def register(app):

    # ── Activation interval-spark-poll uniquement sur / ──────────────────
    @app.callback(
        Output("interval-spark-poll", "disabled"),
        Input("url", "pathname"),
    )
    def toggle_spark_poll(pathname):
        return pathname != "/"

    # ── Clientside : lit window._svgClickParam toutes les 300ms ──────────
    # Quand un tag SVG est cliqué (onclick dans le SVG), il pose
    # window._svgClickParam = "pressure_hp" (par exemple).
    # Ce callback le détecte et met à jour store-spark-param.
    app.clientside_callback(
        """
        function(n_intervals) {
            if (typeof window._svgClickParam === 'string' && window._svgClickParam !== '') {
                var p = window._svgClickParam;
                window._svgClickParam = '';   // reset pour éviter la boucle infinie
                return p;
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("store-spark-param", "data", allow_duplicate=True),
        Input("interval-spark-poll", "n_intervals"),
        prevent_initial_call=True,
    )

    # ── Fermeture du modal (croix OU clic sur backdrop) ──────────────────
    @app.callback(
        Output("store-spark-param", "data", allow_duplicate=True),
        Input("spark-modal-close",    "n_clicks"),
        Input("spark-modal-backdrop", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_spark_modal(_c, _b):
        return None

    # ── Ouverture / fermeture visuelle du modal + titre ──────────────────
    @app.callback(
        Output("spark-modal",       "style"),
        Output("spark-modal-title", "children"),
        Output("spark-modal-dot",   "style"),
        Input("store-spark-param",  "data"),
    )
    def toggle_spark_modal(param):
        if not param:
            return {"display": "none"}, "", {"display": "none"}
        cfg = _SPARK_PARAMS.get(param, _SPARK_PARAMS["active_power"])
        title = f"Tendance — {cfg['label']} ({cfg['unit']})" if cfg["unit"] else f"Tendance — {cfg['label']}"
        dot_style = {
            "color":      cfg["color"],
            "fontSize":   "11px",
            "marginRight": "8px",
        }
        return {"display": "block"}, title, dot_style

    # ── Mise à jour du mini-sparkline ────────────────────────────────────
    # Source : store-history (dernier 300 points WS, ~2m30s)
    # Déclenché à chaque nouveau push WS (store-history se met à jour en cascade)
    @app.callback(
        Output("spark-chart",       "figure"),
        Output("spark-param-label", "children"),
        Input("store-history",      "data"),
        Input("store-spark-param",  "data"),
        State("url",                "pathname"),
        prevent_initial_call=True,
    )
    def update_sparkline(history, param, pathname):
        if pathname != "/" or not param:
            return no_update, no_update

        cfg = _SPARK_PARAMS.get(param, _SPARK_PARAMS["active_power"])
        color  = cfg["color"]
        unit   = cfg["unit"]

        if not history:
            return make_empty_spark_figure(param), ""

        # Extraire x / y depuis l'historique (ordre chronologique)
        xs, ys = [], []
        for pt in history:
            ts = pt.get("timestamp", "")
            v  = pt.get(param)
            if ts and v is not None:
                xs.append(ts[:19])
                ys.append(v)

        if not xs:
            return make_empty_spark_figure(param), ""

        # Construire la figure — échelle Y fixe par paramètre (pas d'auto-scale)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines",
            line={"color": color, "width": 2.0},
            hovertemplate=f"%{{y:.2f}} {unit}<extra></extra>",
        ))
        # Ligne pointillée de la valeur actuelle
        fig.add_hline(
            y=ys[-1],
            line_dash="dot",
            line_color=_hex_to_rgba(color, 0.55),
            line_width=1.2,
        )
        # uirevision = param : réinitialise le zoom si l'utilisateur change de paramètre,
        # mais le préserve si c'est juste une mise à jour de données du même paramètre.
        fig.update_layout(**_SPARK_LAYOUT_BASE, uirevision=param)
        fig.update_yaxes(range=cfg["y_range"])

        n_pts  = len(ys)
        v_last = f"{ys[-1]:.2f} {unit}" if ys else "—"
        v_min  = f"{min(ys):.2f}"
        v_max  = f"{max(ys):.2f}"
        v_avg  = f"{sum(ys)/n_pts:.2f}"
        label  = (
            f"min: {v_min} · moy: {v_avg} · max: {v_max} {unit}"
            f"  ·  {n_pts} pts  ·  val. actuelle : {v_last}"
        )
        return fig, label

    # ── Horloge ──────────────────────────────────────────────────────────
    @app.callback(
        Output("topbar-time", "children"),
        Input("interval-fast", "n_intervals"),
        Input("interval-slow", "n_intervals"),
    )
    def update_clock(_a, _b):
        return datetime.now().strftime("%d/%m/%Y  %H:%M:%S")

    # ── Status Pill ───────────────────────────────────────────────────────
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

    # ── Panneau état système ──────────────────────────────────────────────
    @app.callback(
        Output("dash-state-panel", "children"),
        Input("store-current-data", "data"),
        State("url", "pathname"),
    )
    def update_dash_state_panel(d, pathname):
        if pathname != "/":
            return no_update
        d = d or {}

        status  = d.get("status", "NORMAL")
        s_color = {"NORMAL": "#10b981", "DEGRADED": "#f59e0b",
                   "CRITICAL": "#ef4444"}.get(status, "#10b981")

        valves = [
            ("V1",  "valve_v1",  "#f97316"),
            ("V2",  "valve_v2",  "#60a5fa"),
            ("V3",  "valve_v3",  "#60a5fa"),
            ("BP",  "valve_bp",  "#38bdf8"),
        ]

        return [
            html.Div([
                html.Div("État Système", className="card-title",
                         style={"marginBottom": "0"}),
                html.Span(status, style={"color": s_color, "fontWeight": "700",
                             "fontFamily": "Share Tech Mono", "fontSize": "11px"}),
            ], style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center", "marginBottom": "8px",
                "borderBottom": "1px solid #1e3a5f", "paddingBottom": "6px",
            }),

            html.Div([
                html.Div([
                    html.Div([
                        html.Span(f"{name}:", style={"color": "#475569", "width": "28px",
                                                     "display": "inline-block"}),
                        html.Span(f"{d.get(key, 0):.0f}%", style={
                            "color": col if d.get(key, 0) > 30 else "#ef4444",
                            "fontWeight": "700",
                        }),
                    ], style={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                              "height": "22px", "display": "flex", "alignItems": "center"})
                    for name, key, col in valves
                ]),
                html.Div([
                    html.Div([
                        html.Span(f"{label}:", style={"color": "#475569", "width": "70px",
                                                      "display": "inline-block"}),
                        html.Span(f"{val}", style={"color": col, "fontWeight": "700"}),
                    ], style={"fontFamily": "Share Tech Mono", "fontSize": "11px",
                              "height": "22px", "display": "flex", "alignItems": "center"})
                    for label, val, col in [
                        ("P active",   f"{d.get('active_power', 0):.1f} MW",   "#10b981"),
                        ("Vitesse",    f"{d.get('turbine_speed', 0):.0f} RPM", "#60a5fa"),
                        ("Rendement",  f"{d.get('efficiency', 0):.1f} %",      "#38bdf8"),
                        ("P barillet", f"{d.get('pressure_bp_barillet', 3.0):.2f} bar",
                                       "#ef4444" if d.get("pressure_bp_barillet", 3.0) > 5
                                       else "#a78bfa"),
                        ("cos φ",      f"{d.get('power_factor', 0):.3f}",      "#fbbf24"),
                    ]
                ]),
            ], style={"display": "flex", "justifyContent": "space-between", "gap": "12px"}),
        ]

    # ── Alertes ──────────────────────────────────────────────────────────
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

    # ── Acquittement alertes ─────────────────────────────────────────────
    from dash import MATCH

    @app.callback(
        Output({"type": "ack-btn", "index": MATCH}, "children"),
        Output({"type": "ack-btn", "index": MATCH}, "disabled"),
        Input({"type": "ack-btn", "index": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
    def acknowledge_alert(n_clicks):
        if not n_clicks:
            return no_update, no_update
        if not ctx_cb.triggered:
            return no_update, no_update
        try:
            btn_id   = json.loads(ctx_cb.triggered[0]["prop_id"].split(".")[0])
            alert_id = btn_id["index"]
            r = _session.post(
                f"{BACKEND}/settings/alerts/{alert_id}/acknowledge", timeout=1
            )
            if r.status_code == 200:
                return "OK", True
        except Exception as e:
            print("Erreur acquittement:", e)
        return "Erreur", False

    # ── Synoptique (clientside_callback JS) ──────────────────────────────
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