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
from dash import Input, Output, State, html, no_update, Patch, ctx, callback_context as ctx_cb, ALL
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
    # Plages étroites centrées sur NOMINAL — amplifie la variance visible (style recorder industriel)
    "active_power":   {"label": "P active",  "unit": "MW",  "color": "#10b981", "y_range": [20.5 , 23.5]},
    "pressure_hp":    {"label": "P HP",      "unit": "bar", "color": "#f97316", "y_range": [58,  62]},
    "steam_flow_hp":  {"label": "Débit HP",  "unit": "T/h", "color": "#06b6d4", "y_range": [115,  125]},
    "turbine_speed":  {"label": "Vitesse",   "unit": "RPM", "color": "#818cf8", "y_range": [6325, 6525]},
    "temperature_hp": {"label": "T HP",      "unit": "°C",  "color": "#ef4444", "y_range": [420,  455]},
    "efficiency":           {"label": "Rendement", "unit": "%",   "color": "#38bdf8", "y_range": [58,    59.75]},
    "power_factor":         {"label": "cosφ",      "unit": "",    "color": "#fbbf24", "y_range": [0.8555, 0.8585]},
    "pressure_bp_in":       {"label": "P BP",      "unit": "bar", "color": "#38bdf8", "y_range": [4.2,   4.55]},
    "steam_flow_condenser": {"label": "Q cond.",   "unit": "T/h", "color": "#7dd3fc", "y_range": [84,    94]},
    "current_a":            {"label": "Courant",   "unit": "A",   "color": "#60a5fa", "y_range": [1360, 1485]},
    "apparent_power":       {"label": "S app.",    "unit": "MVA", "color": "#a78bfa", "y_range": [25,    27]},
    "reactive_power":       {"label": "Q réact.",  "unit": "MVAR","color": "#818cf8", "y_range": [12.75,    14]},
}

_PARAM_GROUPS = {
    "__turbine_int__": {
        "label":  "Turbine",
        "color":  "#38bdf8",
        "params": ["efficiency", "pressure_bp_in", "steam_flow_condenser"],
    },
    "__alternateur__": {
        "label":  "Alternateur",
        "color":  "#10b981",
        "params": ["power_factor", "current_a", "apparent_power", "reactive_power"],
    },
}


def _resolve_param(param, idx):
    if param in _PARAM_GROUPS:
        ps = _PARAM_GROUPS[param]["params"]
        return ps[(idx or 0) % len(ps)]
    return param

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

    # ── Ouverture / fermeture visuelle du modal ──────────────────────────
    @app.callback(
        Output("spark-modal",          "style"),
        Output("spark-nav-bar",        "style"),
        Output("store-spark-group-idx","data"),
        Input("store-spark-param",     "data"),
    )
    def toggle_spark_modal(param):
        hidden      = {"display": "none"}
        nav_hidden  = {"display": "none"}
        nav_flex    = {
            "display": "flex", "gap": "6px", "flexWrap": "wrap",
            "paddingBottom": "8px", "marginBottom": "6px",
            "borderBottom": "1px solid #1e3a5f",
        }
        if not param:
            return hidden, nav_hidden, 0
        if param in _PARAM_GROUPS:
            return {"display": "block"}, nav_flex, 0
        return {"display": "block"}, nav_hidden, 0

    # ── Titre + dot + onglets nav ─────────────────────────────────────────
    @app.callback(
        Output("spark-modal-title",    "children"),
        Output("spark-modal-dot",      "style"),
        Output("spark-nav-bar",        "children"),
        Input("store-spark-param",     "data"),
        Input("store-spark-group-idx", "data"),
    )
    def update_spark_header(param, group_idx):
        if not param:
            return "", {"display": "none"}, []

        if param in _PARAM_GROUPS:
            grp      = _PARAM_GROUPS[param]
            group_idx = group_idx or 0
            actual   = _resolve_param(param, group_idx)
            cfg_act  = _SPARK_PARAMS.get(actual, _SPARK_PARAMS["active_power"])
            title    = (
                f"{grp['label']} — {cfg_act['label']}"
                + (f" ({cfg_act['unit']})" if cfg_act["unit"] else "")
            )
            dot_style = {"color": cfg_act["color"], "fontSize": "11px", "marginRight": "8px"}

            tabs = []
            for i, p in enumerate(grp["params"]):
                pc = _SPARK_PARAMS.get(p, _SPARK_PARAMS["active_power"])
                active = i == group_idx
                tabs.append(html.Button(
                    pc["label"],
                    id={"type": "spark-tab", "index": i},
                    n_clicks=0,
                    style={
                        "background":    pc["color"] if active else "rgba(30,58,95,0.4)",
                        "color":         "#0a101a" if active else "#94a3b8",
                        "border":        f"1px solid {pc['color']}",
                        "borderRadius":  "12px",
                        "padding":       "3px 12px",
                        "fontSize":      "10px",
                        "fontFamily":    "Share Tech Mono",
                        "fontWeight":    "700",
                        "cursor":        "pointer",
                        "letterSpacing": "0.5px",
                    },
                ))
            return title, dot_style, tabs

        cfg = _SPARK_PARAMS.get(param, _SPARK_PARAMS["active_power"])
        title = f"Tendance — {cfg['label']}" + (f" ({cfg['unit']})" if cfg["unit"] else "")
        dot_style = {"color": cfg["color"], "fontSize": "11px", "marginRight": "8px"}
        return title, dot_style, []

    # ── Clic sur un onglet → met à jour l'index du groupe ─────────────────
    @app.callback(
        Output("store-spark-group-idx", "data", allow_duplicate=True),
        Input({"type": "spark-tab", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def spark_tab_click(n_clicks_list):
        if not ctx.triggered_id:
            return no_update
        return ctx.triggered_id["index"]

    # ── Mise à jour du mini-sparkline ────────────────────────────────────
    # Source : store-history (dernier 300 points WS, ~2m30s)
    # Déclenché à chaque nouveau push WS (store-history se met à jour en cascade)
    @app.callback(
        Output("spark-chart",          "figure"),
        Output("spark-param-label",    "children"),
        Input("store-history",         "data"),
        Input("store-spark-param",     "data"),
        Input("store-spark-group-idx", "data"),
        State("url",                   "pathname"),
        prevent_initial_call=True,
    )
    def update_sparkline(history, param, group_idx, pathname):
        if pathname != "/" or not param:
            return no_update, no_update

        actual = _resolve_param(param, group_idx)
        cfg    = _SPARK_PARAMS.get(actual, _SPARK_PARAMS["active_power"])
        color  = cfg["color"]
        unit   = cfg["unit"]

        if not history:
            return make_empty_spark_figure(actual), ""

        # Extraire x / y depuis l'historique (ordre chronologique)
        xs, ys = [], []
        for pt in history:
            ts = pt.get("timestamp", "")
            v  = pt.get(actual)
            if ts and v is not None:
                xs.append(ts[:19])
                ys.append(v)

        if not xs:
            return make_empty_spark_figure(actual), ""

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
        fig.update_layout(**_SPARK_LAYOUT_BASE, uirevision=actual)
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