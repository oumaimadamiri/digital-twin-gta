"""
callbacks/cb_ai.py — Callbacks module IA
"""
import requests
import plotly.graph_objects as go
from dash import Input, Output, html, no_update, ctx, Patch
from config import BACKEND

_session = requests.Session()

_AI_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    legend={"font": {"family": "Inter, sans-serif", "color": "#94a3b8", "size": 9},
            "bgcolor": "rgba(0,0,0,0)"},
    xaxis={"tickfont": {"family": "Share Tech Mono, monospace", "color": "#64748b", "size": 8},
           "gridcolor": "#1e293b", "color": "#334155"},
    yaxis={"tickfont": {"family": "Share Tech Mono, monospace", "color": "#64748b", "size": 8},
           "gridcolor": "#1e293b", "color": "#334155"},
    uirevision="ai",
)
def _timeline_bars(anomaly_history, threshold):
    """Construit les barres colorées de la timeline à partir de l'historique réel AE."""
    if not anomaly_history:
        return [html.Div(className="tl-bar tl-normal", style={"height": "4px"}) for _ in range(20)]

    cap = max(threshold * 3, 1e-9)
    bars = []
    for pt in anomaly_history:
        err = pt.get("reconstruction_error", 0.0)
        pct = min(err / cap, 1.0)
        height = max(4, round(pct * 50))
        if err >= threshold * 2:
            cls = "tl-crit"
        elif err >= threshold:
            cls = "tl-warn"
        else:
            cls = "tl-normal"
        bars.append(html.Div(className=f"tl-bar {cls}", style={"height": f"{height}px"}))

    # Complète à 20 barres si l'historique réel est encore court
    while len(bars) < 20:
        bars.insert(0, html.Div(className="tl-bar tl-normal", style={"height": "4px"}))

    return bars[-20:]

def register(app):

    @app.callback(
        Output("mc-ae-value",        "children"),
        Output("mc-ae-sub",          "children"),
        Output("mc-ae-badge",        "children"),
        Output("mc-ae-badge",        "className"),
        Output("mc-lstm-value",      "children"),
        Output("mc-lstm-sub",        "children"),
        Output("mc-xgb-value",       "children"),
        Output("mc-xgb-sub",         "children"),
        Output("ae-gauge",           "figure"),
        Output("ae-status-label",    "children"),
        Output("ae-timeline",        "children"),
        Output("ae-timeline-start",  "children"),
        Output("lstm-prediction-chart", "figure"),
        Output("rul-value",          "children"),
        Output("rul-progress",       "children"),
        Output("ai-alerts-table",    "children"),
        Output("ai-last-training-badge", "children"),
        Output("ai-alerts-export-link",  "href"),
        Input("interval-ai", "n_intervals"),
        Input("url", "pathname"),
    )
    def update_ai(n_intervals, pathname):
        if pathname != "/ai":
            return [no_update] * 18

        try:
            results = _session.get(f"{BACKEND}/ai/analysis", timeout=8).json()
        except Exception:
            return [no_update] * 18

        if not results or results.get("ready") is False:
            return [no_update] * 18

        try:
            ai_alerts = _session.get(f"{BACKEND}/ai/alerts?limit=10", timeout=2).json()
        except Exception:
            ai_alerts = []

        anomaly = results.get("anomaly_detection", {})
        lstm    = results.get("lstm_prediction",   {})
        rul     = results.get("rul_estimation",    {})
        ae_hist = results.get("anomaly_history",   [])

        is_initial = (not n_intervals) or (ctx.triggered_id == "url")
        # ── Carte Autoencodeur ──────────────────────────────────────────
        err      = anomaly.get("reconstruction_error", 0.0)
        is_anom  = anomaly.get("is_anomaly", False)
        thresh   = anomaly.get("threshold", 0.05)
        ae_color = "#ff3d57" if is_anom else "#00e676"

        mc_ae_value = f"{err:.4f}"
        mc_ae_sub   = (f"Seuil critique : {thresh:.3f} · "
                       f"{'Anomalie détectée' if is_anom else 'Reconstruction normale'}")
        mc_ae_badge      = "ANOMALIE" if is_anom else "ACTIF"
        mc_ae_badge_cls  = "mc-badge alert" if is_anom else "mc-badge"

        # ── Jauge AE ──────────────────────────────────────────────────
        if is_initial:
            ae_gauge = go.Figure(go.Indicator(
                mode="gauge+number", value=err,
                number={"font": {"size": 24, "color": ae_color,
                                 "family": "Share Tech Mono, monospace"}, "valueformat": ".4f"},
                gauge={
                    "axis": {"range": [0, thresh * 3], "tickcolor": "#1e293b",
                             "tickfont": {"size": 8, "color": "#64748b"}},
                    "bar":  {"color": ae_color, "thickness": 0.25},
                    "bgcolor": "rgba(0,0,0,0)", "bordercolor": "#1e293b", "borderwidth": 1,
                    "steps": [
                        {"range": [0, thresh],            "color": "rgba(16,185,129,0.15)"},
                        {"range": [thresh, thresh * 2],    "color": "rgba(245,158,11,0.15)"},
                        {"range": [thresh * 2, thresh * 3], "color": "rgba(239,68,68,0.15)"},
                    ],
                    "threshold": {"line": {"color": "#f59e0b", "width": 2},
                                  "value": thresh, "thickness": 0.8},
                },
            ))
            ae_gauge.update_layout(margin={"t": 20, "b": 5, "l": 10, "r": 10}, height=180,
                                   font={"family": "Share Tech Mono, monospace"},
                                   **{k: v for k, v in _AI_LAYOUT_BASE.items()
                                      if k not in ("xaxis", "yaxis", "legend", "uirevision")})
        else:
            ae_gauge = Patch()
            ae_gauge["data"][0]["value"] = err
            ae_gauge["data"][0]["number"]["font"]["color"] = ae_color
            ae_gauge["data"][0]["gauge"]["axis"]["range"] = [0, thresh * 3]
            ae_gauge["data"][0]["gauge"]["bar"]["color"] = ae_color
            ae_gauge["data"][0]["gauge"]["threshold"]["value"] = thresh
            ae_gauge["data"][0]["gauge"]["steps"][1]["range"] = [thresh, thresh * 2]
            ae_gauge["data"][0]["gauge"]["steps"][2]["range"] = [thresh * 2, thresh * 3]

        ae_status = html.Span(
            "⚠ ANOMALIE DÉTECTÉE" if is_anom else "✓ État nominal",
            style={"color": ae_color, "fontFamily": "var(--mono)",
                   "fontSize": "12px", "fontWeight": "700"},
        )

        # ── Timeline réelle (historique des 20 derniers points, ~5s/pt) ──
        timeline_bars = _timeline_bars(ae_hist, thresh)
        n_points      = len(ae_hist) if ae_hist else 20
        timeline_start = f"-{n_points * 5}s"

        # ── Carte LSTM ────────────────────────────────────────────────
        if lstm.get("ready"):
            raw_precision = lstm.get("precision_pct")
            mc_lstm_value = f"{raw_precision:.0f}%" if raw_precision is not None else "—"
            horizon_s = lstm.get("horizon_seconds", 0)
            mc_lstm_sub = f"Horizon : {horizon_s:.0f}s · Précision mesurée en continu"
        else:
            mc_lstm_value = "N/A"
            mc_lstm_sub = "Buffer insuffisant — en cours de constitution"

        # ── Graphique LSTM ─────────────────────────────────────────────
        lstm_fig = go.Figure()
        if lstm.get("ready"):
            features = lstm.get("features", [])
            pred     = lstm.get("predicted_values", [])
            lo       = lstm.get("confidence_lower", [])
            hi       = lstm.get("confidence_upper", [])
            x        = list(range(len(pred)))
            if pred and features:
                for i, feat in enumerate(features[:2]):
                    y_pred = [s[i] if isinstance(s, list) else s for s in pred]
                    y_lo   = [s[i] if isinstance(s, list) else s for s in lo]
                    y_hi   = [s[i] if isinstance(s, list) else s for s in hi]
                    color      = ["#00b4ff", "#00e676"][i % 2]
                    fillcolor  = ["rgba(0,180,255,0.13)", "rgba(0,230,118,0.13)"][i % 2]
                    lstm_fig.add_trace(go.Scatter(x=x, y=y_pred, name=feat,
                                                  line={"color": color, "width": 2}))
                    lstm_fig.add_trace(go.Scatter(x=x + x[::-1], y=y_hi + y_lo[::-1],
                                                  fill="toself", fillcolor=fillcolor,
                                                  line={"color": "rgba(0,0,0,0)"},
                                                  showlegend=False))
        
        lstm_fig.update_layout(
            margin={"t": 10, "b": 20, "l": 40, "r": 10},
            xaxis={**_AI_LAYOUT_BASE["xaxis"],
                   "title": {"text": "Horizon (×500ms)",
                              "font": {"family": "Share Tech Mono, monospace",
                                       "color": "#64748b", "size": 9}}},
            **{k: v for k, v in _AI_LAYOUT_BASE.items() if k != "xaxis"},
        )

        # ── RUL ───────────────────────────────────────────────────────
        rul_days = rul.get("rul_days", 0.0)
        if rul_days > 20:
            rul_color = "#00e676"
            rul_label = f"{rul_days:.0f} j"
        elif rul_days > 7:
            rul_color = "#ffd740"
            rul_label = f"{rul_days:.0f} j"
        else:
            rul_color = "#ff3d57"
            rul_label = f"{rul_days:.1f} j"

        progress_pct = min(rul_days / 30 * 100, 100)

        mc_xgb_value = rul_label
        mc_xgb_sub   = f"Maintenance recommandée : {rul.get('estimated_failure', 'N/A')}"
        rul_progress = html.Div([
            html.Div(className="rul-bar", children=[
                html.Div(className="rul-fill", style={
                    "width": f"{progress_pct:.0f}%",
                    "background": rul_color,
                }),
            ]),
            html.Div([
                html.Span("Date estimée de panne : ", style={"color": "var(--text3)"}),
                html.Span(
                    rul.get("estimated_failure", "N/A"),
                    style={"color": rul_color, "fontWeight": "700" if rul_days <= 7 else "400"},
                ),
            ], className="rul-sub", style={"marginBottom": "4px"}),
            html.Div([
                html.Span("Score dégradation : ", style={"color": "var(--text3)"}),
                html.Span(f"{rul.get('degradation_score', 0.0):.3f}",
                          style={"color": rul_color, "fontFamily": "var(--mono)"}),
                html.Span("  |  Paramètre critique : ", style={"color": "var(--text3)"}),
                html.Span(rul.get("critical_parameter", "N/A"),
                          style={"color": "#aa80ff", "fontFamily": "var(--mono)"}),
            ], className="rul-sub"),
        ])

        # ── Alertes IA ────────────────────────────────────────────────
        if not ai_alerts:
            tbl = html.Div("Aucune alerte IA",
                           style={"color": "var(--text3)", "fontFamily": "var(--mono)",
                                  "fontSize": "12px", "padding": "10px"})
        else:
            hdr = html.Tr([html.Th(h) for h in
                           ["Timestamp", "Type", "Paramètre", "Valeur", "Seuil", "Statut"]])
            rows = [html.Tr([
                html.Td(a.get("timestamp", "")[:19].replace("T", " ")),
                html.Td(a.get("alert_type", "")),
                html.Td(a.get("parameter", "")),
                html.Td(f"{a.get('value', 0):.3f}"),
                html.Td(f"{a.get('threshold', 0):.3f}"),
                html.Td(html.Span(a.get("severity", ""),
                                  className=f"status-pill "
                                            f"{'critical' if a.get('severity') == 'CRITICAL' else 'degraded'}")),
            ]) for a in ai_alerts[:8]]
            tbl = html.Table([html.Thead(hdr), html.Tbody(rows)], className="data-table")

        last_training = f"🔄 Dernier réentraînement : {results.get('last_training', 'N/A')}"
        export_href = f"{BACKEND}/ai/alerts/export/csv"

        return (mc_ae_value, mc_ae_sub, mc_ae_badge, mc_ae_badge_cls,
                mc_lstm_value, mc_lstm_sub,
                mc_xgb_value, mc_xgb_sub,
                ae_gauge, ae_status, timeline_bars, timeline_start,
                lstm_fig, rul_label, rul_progress, tbl,
                last_training, export_href)
    # ── Bouton analyse manuelle ────────────────────────────────────────
    @app.callback(
        Output("ai-run-status", "children"),
        Input("btn-run-ai", "n_clicks"),
        prevent_initial_call=True,
    )
    def run_ai_manual(_):
        try:
            _session.get(f"{BACKEND}/ai/analysis", timeout=5)
            from datetime import datetime
            return f"Analyse lancée à {datetime.now().strftime('%H:%M:%S')}"
        except Exception as e:
            return f"Erreur : {e}"