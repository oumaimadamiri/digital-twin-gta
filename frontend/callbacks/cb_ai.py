"""
callbacks/cb_ai.py — Callbacks module IA
CORRECTIONS :
  1. lstm-precision-value n'est plus hardcodé à "92%" — valeur réelle ou "N/A"
  2. RUL : affichage couleur dynamique + tendance visuelle
  3. prevent_initial_call=True conservé
"""
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update, ctx, Patch
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


def register(app):

    @app.callback(
        Output("ae-error-value",      "children"),
        Output("ae-error-value",      "style"),
        Output("lstm-precision-value","children"),
        Output("rul-value",           "children"),
        Output("ae-gauge",            "figure"),
        Output("lstm-prediction-chart","figure"),
        Output("ae-status-label",     "children"),
        Output("rul-progress",        "children"),
        Output("ai-alerts-table",     "children"),
        Input("interval-ai", "n_intervals"),
        Input("url", "pathname"),
    )
    def update_ai(n_intervals, pathname):
        if pathname != "/ai":
            return [no_update] * 9

        try:
            results = _session.get(f"{BACKEND}/ai/analysis", timeout=2).json()
        except Exception:
            results = {}

        try:
            ai_alerts = _session.get(f"{BACKEND}/ai/alerts?limit=10", timeout=1).json()
        except Exception:
            ai_alerts = []

        anomaly = results.get("anomaly_detection", {})
        lstm    = results.get("lstm_prediction",   {})
        rul     = results.get("rul_estimation",    {})

        is_initial = (not n_intervals) or (ctx.triggered_id == "url")

        # ── Autoencodeur ──────────────────────────────────────────────
        err      = anomaly.get("reconstruction_error", 0.0)
        is_anom  = anomaly.get("is_anomaly", False)
        ae_color = "#ff3d57" if is_anom else "#00e676"
        ae_style = {"fontFamily": "var(--mono)", "fontSize": "32px",
                    "fontWeight": "700", "color": ae_color}

        thresh = anomaly.get("threshold", 0.05)
        
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
                        {"range": [0, thresh],        "color": "rgba(16,185,129,0.1)"},
                        {"range": [thresh, thresh*3],  "color": "rgba(239,68,68,0.1)"},
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

        ae_status = html.Span(
            "⚠ ANOMALIE DÉTECTÉE" if is_anom else "✓ État nominal",
            style={"color": ae_color, "fontFamily": "var(--mono)",
                   "fontSize": "12px", "fontWeight": "700"},
        )

        # ── LSTM — précision RÉELLE mesurée en continu ────────────────
        if lstm.get("ready"):
            raw_precision = lstm.get("precision_pct")
            if raw_precision is not None:
                lstm_precision_text = f"{raw_precision:.0f}%"
            else:
                lstm_precision_text = "Calcul en cours…"
        else:
            lstm_precision_text = "N/A"

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

        # ── RUL — affichage couleur + tendance ────────────────────────
        rul_days  = rul.get("rul_days", 0.0)
        if rul_days > 20:
            rul_color = "#00e676"
            rul_label = f"{rul_days:.0f} j"
        elif rul_days > 7:
            rul_color = "#ffd740"
            rul_label = f"{rul_days:.0f} j"
        else:
            rul_color = "#ff3d57"
            rul_label = f"{rul_days:.1f} j"

        # Barre de progression : 0j = vide, 30j = plein
        progress_pct = min(rul_days / 30 * 100, 100)

        rul_progress = html.Div([
            html.Div([
                html.Span("Date estimée de panne : ",
                          style={"color": "var(--text3)", "fontSize": "11px"}),
                html.Span(
                    rul.get("estimated_failure", "N/A"),
                    style={"color": rul_color, "fontFamily": "var(--mono)", "fontSize": "12px",
                           "fontWeight": "700" if rul_days <= 7 else "400"},
                ),
            ], style={"marginBottom": "8px", "display": "flex", "alignItems": "center",
                      "gap": "6px"}),

            # Barre de progression
            html.Div(style={
                "height": "6px", "borderRadius": "3px",
                "background": f"linear-gradient(90deg, {rul_color} {progress_pct:.0f}%, #1e293b 0%)",
                "marginBottom": "6px",
            }),

            html.Div([
                html.Span(f"Score dégradation : ",
                          style={"color": "var(--text3)", "fontSize": "10px"}),
                html.Span(
                    f"{rul.get('degradation_score', 0.0):.3f}",
                    style={"color": rul_color, "fontFamily": "var(--mono)", "fontSize": "10px"},
                ),
                html.Span(f"  |  Paramètre critique : ",
                          style={"color": "var(--text3)", "fontSize": "10px"}),
                html.Span(
                    rul.get("critical_parameter", "N/A"),
                    style={"color": "#aa80ff", "fontFamily": "var(--mono)", "fontSize": "10px"},
                ),
            ]),
        ], style={"marginTop": "10px"})

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

        return (f"{err:.4f}", ae_style, lstm_precision_text, rul_label,
                ae_gauge, lstm_fig, ae_status, rul_progress, tbl)

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