"""
components/alert_banner.py — Bannières d'alertes
"""
from dash import html


def alert_item(a):
    sev = a.get("severity", "INFO").lower()
    css = {"critical": "critical", "warning": "warning", "info": "info"}.get(sev, "info")
    icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(css, "⚪")
    ts = a.get("timestamp", "")[:19].replace("T", " ")
    return html.Div([
        html.Span(icon),
        html.Div([
            html.Span(f"[{a.get('source','')}] {a.get('parameter','').upper()} = {a.get('value',0):.2f} ",
                      style={"fontWeight": "700"}),
            html.Span(f"(seuil: {a.get('threshold',0):.2f})", style={"opacity": "0.7"}),
        ], style={"flex": "1"}),
        html.Span(ts, style={"opacity": "0.5", "fontSize": "10px", "whiteSpace": "nowrap"}),
    ], className=f"alert-banner {css}")


def alerts_panel(alerts):
    if not alerts:
        return html.Div("✅  Aucune alerte active — système nominal",
                        style={"color": "#00e676", "fontFamily": "Share Tech Mono",
                               "fontSize": "12px", "padding": "10px"})
    return html.Div([alert_item(a) for a in alerts[:10]])