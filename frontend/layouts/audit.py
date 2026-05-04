"""
layouts/audit.py — Journal opérateur (audit trail)
ISA-95 niveau 1-2 : traçabilité de toutes les actions opérateur
"""
from dash import html, dcc
from components.sidebar import create_sidebar

_ACTION_LABELS = {
    "VALVE_COMMAND":    "Commande vanne",
    "SCENARIO_TRIGGER": "Déclenchement scénario",
    "SCENARIO_STOP":    "Arrêt scénario",
    "RESET":            "Réinitialisation",
    "THRESHOLD_UPDATE": "Modification seuils",
    "ALERT_ACK":        "Acquittement alarme",
}

_SOURCE_COLORS = {
    "OPERATOR": "#818cf8",
    "SYSTEM":   "#ef4444",
    "INTERLOCK": "#f59e0b",
}


def layout():
    return html.Div([
        create_sidebar(active_path="/journal"),
        html.Div([

            # ── Titre ────────────────────────────────────────────────────
            html.Div([
                html.Div("Journal Opérateur", className="card-title",
                         style={"fontSize": "18px", "marginBottom": "4px"}),
                html.Div("Traçabilité ISA-95 — toutes les actions sont horodatées",
                         style={"color": "var(--text3)", "fontSize": "11px",
                                "fontFamily": "var(--mono)"}),
            ], style={"marginBottom": "16px"}),

            # ── Filtres ───────────────────────────────────────────────────
            html.Div([
                html.Div([
                    html.Div("Type d'action", className="filter-label"),
                    dcc.Dropdown(
                        id="journal-filter-type",
                        options=[{"label": "Tous", "value": "ALL"}] +
                                [{"label": v, "value": k} for k, v in _ACTION_LABELS.items()],
                        value="ALL",
                        clearable=False,
                        className="custom-dropdown",
                        style={"width": "200px"},
                    ),
                ], style={"flex": "1"}),
                html.Div([
                    html.Div("Source", className="filter-label"),
                    dcc.Dropdown(
                        id="journal-filter-source",
                        options=[
                            {"label": "Toutes", "value": "ALL"},
                            {"label": "Opérateur", "value": "OPERATOR"},
                            {"label": "Système (auto)", "value": "SYSTEM"},
                        ],
                        value="ALL",
                        clearable=False,
                        className="custom-dropdown",
                        style={"width": "180px"},
                    ),
                ], style={"flex": "1"}),
                html.Div([
                    html.Div("Nombre d'entrées", className="filter-label"),
                    dcc.Dropdown(
                        id="journal-limit",
                        options=[{"label": str(n), "value": n} for n in [50, 100, 200, 500]],
                        value=100,
                        clearable=False,
                        className="custom-dropdown",
                        style={"width": "120px"},
                    ),
                ], style={"flex": "0"}),
                html.Div([
                    html.Div(" ", className="filter-label"),
                    html.Button("Rafraîchir", id="journal-refresh-btn",
                                className="btn btn-primary",
                                style={"height": "36px", "padding": "0 16px"}),
                ], style={"flex": "0"}),
                html.Div([
                    html.Div(" ", className="filter-label"),
                    html.A("⬇ Export CSV",
                           id="journal-export-link",
                           href="#",
                           className="btn btn-warn",
                           style={"height": "36px", "padding": "0 16px",
                                  "display": "flex", "alignItems": "center",
                                  "textDecoration": "none"}),
                ], style={"flex": "0"}),
            ], style={"display": "flex", "gap": "16px", "alignItems": "flex-end",
                      "flexWrap": "wrap", "marginBottom": "16px"}),

            # ── Compteur ──────────────────────────────────────────────────
            html.Div(id="journal-count",
                     style={"color": "var(--text3)", "fontSize": "11px",
                            "fontFamily": "var(--mono)", "marginBottom": "8px"}),

            # ── Tableau ───────────────────────────────────────────────────
            html.Div(id="journal-table-container",
                     style={"overflowX": "auto"}),

            # Rafraîchissement automatique toutes les 10 s sur la page
            dcc.Interval(id="journal-interval", interval=10_000, n_intervals=0),

        ], className="page-content"),
    ], className="main-content-wrap")
