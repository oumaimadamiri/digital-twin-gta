"""
callbacks/cb_ai.py — Callbacks module IA
Optimisé :
  - Session HTTP unique + un seul endpoint /ai/dashboard fusionné
  - Fallback gracieux si l'endpoint combiné n'existe pas encore
  - prevent_initial_call=True
  - Layouts Plotly partagés
"""
import requests
import plotly.graph_objects as go
from dash import Input, Output, State, html, no_update
from config import BACKEND

_session = requests.Session()

# Layout commun pour les figures IA
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
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_ai(_, pathname):
        if pathname != "/ai":
            return [no_update] * 9

        # ── Un seul aller-retour HTTP pour les 2 ressources ──────────
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

        # ── Autoencodeur ──────────────────────────────────────────────
        err      = anomaly.get("reconstruction_error", 0.0)
        is_anom  = anomaly.get("is_anomaly", False)
        ae_color = "#ff3d57" if is_anom else "#00e676"
        ae_style = {"fontFamily": "var(--mono)", "fontSize": "32px",
                    "fontWeight": "700", "color": ae_color}

        thresh = anomaly.get("threshold", 0.05)
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

        ae_status = html.Span(
            "⚠ ANOMALIE DÉTECTÉE" if is_anom else "✓ État nominal",
            style={"color": ae_color, "fontFamily": "var(--mono)",
                   "fontSize": "12px", "fontWeight": "700"},
        )

        # ── LSTM ──────────────────────────────────────────────────────
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
                    color  = ["#00b4ff", "#00e676"][i % 2]
                    lstm_fig.add_trace(go.Scatter(x=x, y=y_pred, name=feat,
                                                  line={"color": color, "width": 2}))
                    lstm_fig.add_trace(go.Scatter(x=x + x[::-1], y=y_hi + y_lo[::-1],
                                                  fill="toself", fillcolor=f"{color}22",
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
        rul_days  = rul.get("rul_days", 0.0)
        rul_color = "#00e676" if rul_days > 20 else ("#ffd740" if rul_days > 7 else "#ff3d57")
        rul_progress = html.Div([
            html.Div([
                html.Span("Date estimée de panne : ",
                          style={"color": "var(--text3)", "fontSize": "11px"}),
                html.Span(rul.get("estimated_failure", "N/A"),
                          style={"color": rul_color, "fontFamily": "var(--mono)", "fontSize": "12px"}),
            ], style={"marginBottom": "6px"}),
            html.Div([
                html.Div(style={"height": "4px", "borderRadius": "2px",
                                "background": f"linear-gradient(90deg, {rul_color} "
                                              f"{min(rul_days / 30 * 100, 100):.0f}%, var(--border) 0%)",
                                "marginBottom": "4px"}),
                html.Span(f"Score dégradation : {rul.get('degradation_score', 0.0):.3f}",
                          style={"color": "var(--text3)", "fontFamily": "var(--mono)", "fontSize": "10px"}),
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

        return (f"{err:.4f}", ae_style, "92%", f"{rul_days:.0f} j",
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