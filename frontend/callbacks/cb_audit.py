"""
callbacks/cb_audit.py — Journal opérateur (audit trail)
"""
import requests
from dash import Input, Output, State, html, no_update
from config import BACKEND

_session = requests.Session()

_ACTION_LABELS = {
    "VALVE_COMMAND":    "Commande vanne",
    "SCENARIO_TRIGGER": "Déclenchement scénario",
    "SCENARIO_STOP":    "Arrêt scénario",
    "RESET":            "Réinitialisation",
    "THRESHOLD_UPDATE": "Modification seuils",
    "ALERT_ACK":        "Acquittement alarme",
}

_SOURCE_COLORS = {
    "OPERATOR":  "#818cf8",
    "SYSTEM":    "#ef4444",
    "INTERLOCK": "#f59e0b",
}

_TYPE_COLORS = {
    "VALVE_COMMAND":    "#38bdf8",
    "SCENARIO_TRIGGER": "#f59e0b",
    "SCENARIO_STOP":    "#94a3b8",
    "RESET":            "#10b981",
    "THRESHOLD_UPDATE": "#c084fc",
    "ALERT_ACK":        "#fb923c",
}


def _make_table(rows: list) -> html.Div:
    if not rows:
        return html.Div("Aucune action enregistrée.",
                        style={"color": "var(--text3)", "fontFamily": "var(--mono)",
                               "padding": "20px"})

    header = html.Tr([
        html.Th(col, style={
            "textAlign": "left", "padding": "8px 12px",
            "fontFamily": "var(--ui)", "fontSize": "11px",
            "fontWeight": "700", "color": "var(--text3)",
            "borderBottom": "1px solid var(--border)",
            "whiteSpace": "nowrap",
        })
        for col in ["Horodatage", "Opérateur", "Source", "Action", "Cible",
                    "Avant", "Après", "Notes"]
    ])

    data_rows = []
    for i, row in enumerate(rows):
        src   = row.get("source", "OPERATOR")
        atype = row.get("action_type", "")
        bg    = "rgba(255,255,255,0.02)" if i % 2 == 0 else "transparent"

        def cell(val, color=None, mono=False):
            style = {
                "padding": "7px 12px",
                "fontSize": "11px",
                "fontFamily": "var(--mono)" if mono else "var(--ui)",
                "color": color or "var(--text)",
                "borderBottom": "1px solid rgba(255,255,255,0.04)",
                "maxWidth": "180px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            }
            return html.Td(str(val) if val is not None else "—", style=style, title=str(val) if val else "")

        data_rows.append(html.Tr([
            cell(row.get("ts", "")[:19], mono=True),
            cell(row.get("user", "—"), color="#e2e8f0"),
            cell(src,  color=_SOURCE_COLORS.get(src, "#94a3b8")),
            cell(_ACTION_LABELS.get(atype, atype), color=_TYPE_COLORS.get(atype, "#94a3b8")),
            cell(row.get("target"), mono=True),
            cell(row.get("value_before"), color="#94a3b8", mono=True),
            cell(row.get("value_after"),  color="#10b981", mono=True),
            cell(row.get("notes"),        color="#f59e0b"),
        ], style={"background": bg}))

    return html.Table(
        [html.Thead(header), html.Tbody(data_rows)],
        style={
            "width": "100%",
            "borderCollapse": "collapse",
            "fontFamily": "var(--mono)",
        },
    )


def register(app):

    @app.callback(
        Output("journal-table-container", "children"),
        Output("journal-count", "children"),
        Output("journal-export-link", "href"),
        Input("journal-interval", "n_intervals"),
        Input("journal-refresh-btn", "n_clicks"),
        Input("url", "pathname"),
        State("journal-filter-type",   "value"),
        State("journal-filter-source", "value"),
        State("journal-limit",         "value"),
        prevent_initial_call=False,
    )
    def refresh_journal(_, _btn, pathname, ftype, fsource, limit):
        if pathname != "/journal":
            return no_update, no_update, no_update

        params = {"limit": limit or 100}
        try:
            r = _session.get(f"{BACKEND}/audit/operator-actions", params=params, timeout=3)
            rows = r.json() if r.status_code == 200 else []
        except Exception:
            rows = []

        # Filtres locaux (type et source)
        if ftype and ftype != "ALL":
            rows = [r for r in rows if r.get("action_type") == ftype]
        if fsource and fsource != "ALL":
            rows = [r for r in rows if r.get("source") == fsource]

        table  = _make_table(rows)
        count  = f"{len(rows)} action(s) affichée(s)"
        export = f"{BACKEND}/audit/operator-actions/export/csv"
        return table, count, export
