import json
from datetime import datetime
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, Patch
from components.alert_banner import alerts_panel
from config import BACKEND

_session = requests.Session()

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


def make_empty_rt_figure():
    """Figure RT vide initialisée avec toutes les traces."""
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
    return len(fig.get("data", [])) == len(_RT_PARAMS)


def register(app):

    # ── Horloge ──────────────────────────────────────────────────────
    @app.callback(
        Output("topbar-time", "children"),
        Input("interval-fast", "n_intervals"),
        Input("interval-slow",  "n_intervals"),
    )
    def update_clock(_a, _b):
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

    # ── Panneau état système ──────────────────────────────────────────
    @app.callback(
        Output("dash-state-panel", "children"),
        Input("store-current-data", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
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
            ("MP",  "valve_mp",  "#a78bfa"),
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
                # Vannes
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

                # Params
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
                                       "#ef4444" if d.get("pressure_bp_barillet", 3.0) > 3.5
                                       else "#a78bfa"),
                        ("cos φ",      f"{d.get('power_factor', 0):.3f}",      "#fbbf24"),
                    ]
                ]),
            ], style={"display": "flex", "justifyContent": "space-between", "gap": "12px"}),
        ]

    # ── Graphique temps réel (Patch ciblé) ────────────────────────────
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
    from dash import MATCH, callback_context as ctx_cb

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