"""
components/alert_banner.py — Bannières d'alertes
"""
from dash import html


def alert_item(a):
    sev = a.get("severity", "INFO").lower()
    css = {"critical": "critical", "warning": "warning", "info": "info"}.get(sev, "info")
    icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(css, "⚪")
    ts = a.get("timestamp", "")[:19].replace("T", " ")
    alert_id = a.get("id")
    is_ack = a.get("acknowledged", False)

    content = [
        html.Span(icon, className="alert-icon"),
        html.Div([
            html.Span(f"[{a.get('source','')}] {a.get('parameter','').upper()} = {a.get('value',0):.2f} ",
                      style={"fontWeight": "700"}),
            html.Span(f"(seuil: {a.get('threshold',0):.2f})", style={"opacity": "0.7"}),
        ], style={"flex": "1"}),
        html.Span(ts, style={"opacity": "0.5", "fontSize": "10px", "whiteSpace": "nowrap", "marginRight": "10px"}),
    ]

    if not is_ack and alert_id is not None:
        content.append(
            html.Button(
                "Acquitter",
                id={"type": "ack-btn", "index": alert_id},
                className="btn-ack",
                style={"cursor": "pointer", "fontSize": "10px", "padding": "2px 5px", "borderRadius": "4px", "border": "1px solid white", "backgroundColor": "transparent", "color": "inherit"}
            )
        )

    return html.Div(content, className=f"alert-banner {css}")

def alerts_panel(alerts):
    if not alerts:
        return html.Div("✅  Aucune alerte active — système nominal",
                        style={"color": "#00e676", "fontFamily": "Share Tech Mono",
                               "fontSize": "12px", "padding": "10px"})
    return html.Div([alert_item(a) for a in alerts[:10]])