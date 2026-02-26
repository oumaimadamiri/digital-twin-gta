"""
layouts/settings.py — Paramètres & Profil
"""
from dash import html, dcc
from components.sidebar import create_sidebar, create_topbar
from config import BACKEND


def threshold_row(label, param, default_min, default_max, unit):
    return html.Div([
        html.Div(label, style={"fontFamily": "var(--ui)", "fontSize": "13px", "fontWeight": "600",
                                "color": "var(--text3)", "width": "180px", "flexShrink": "0"}),
        html.Div([
            html.Span("Min:", style={"color": "var(--text3)", "fontSize": "11px", "marginRight": "6px"}),
            dcc.Input(id=f"thresh-{param}-min", value=default_min, type="number", step=0.1,
                      className="custom-input", style={"width": "80px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
        html.Div([
            html.Span("Max:", style={"color": "var(--text3)", "fontSize": "11px", "marginRight": "6px"}),
            dcc.Input(id=f"thresh-{param}-max", value=default_max, type="number", step=0.1,
                      className="custom-input", style={"width": "80px"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
        html.Div(unit, style={"color": "var(--text3)", "fontSize": "12px", "fontFamily": "var(--mono)"}),
    ], className="settings-row")


def layout():
    return html.Div([
        create_sidebar(active_path="/settings"),
        html.Div([
            create_topbar("Paramètres", "Configuration Système"),

            html.Div([
                html.Div([
                    # ── SEUILS D'ALARME ──────────────────────
                    html.Div([
                        html.Div("Seuils d'Alarme Configurables", className="card-title"),
                        threshold_row("Pression HP",      "pressure_hp",    55.0, 65.0,  "bar"),
                        threshold_row("Température HP",   "temperature_hp", 440.0, 500.0, "°C"),
                        threshold_row("Débit vapeur HP",  "steam_flow_hp",  100.0, 130.0, "T/h"),
                        threshold_row("Vitesse turbine",  "turbine_speed",  6300.0, 6500.0, "RPM"),
                        threshold_row("Puissance active", "active_power",   0.0, 32.0,   "MW"),
                        threshold_row("Facteur cosφ",     "power_factor",   0.80, 0.90,  "—"),
                        threshold_row("Rendement",        "efficiency",     80.0, 100.0, "%"),
                        html.Div([
                            html.Button("💾 Appliquer les seuils", id="btn-save-thresholds",
                                        className="btn btn-success"),
                            html.Div(id="thresh-save-status",
                                     style={"fontFamily": "var(--mono)", "fontSize": "11px",
                                            "color": "var(--text3)", "marginLeft": "12px"}),
                        ], style={"marginTop": "16px", "display": "flex", "alignItems": "center"}),
                    ], className="card", style={"marginBottom": "16px"}),

                    # ── PARAMÈTRES SYSTÈME ────────────────────
                    html.Div([
                        html.Div("Paramètres Système", className="card-title"),
                        html.Div([
                            html.Div([
                                html.Div("Intervalle de rafraîchissement", className="filter-label"),
                                dcc.Dropdown(id="refresh-rate-selector",
                                    options=[{"label": "500ms", "value": 500},
                                             {"label": "1s",    "value": 1000},
                                             {"label": "2s",    "value": 2000}],
                                    value=500, clearable=False,
                                    className="custom-dropdown",
                                    style={"width": "150px"}),
                            ], style={"flex": "1"}),
                            html.Div([
                                html.Div("Notifications", className="filter-label"),
                                dcc.Checklist(id="notif-options",
                                    options=[{"label": " Alertes critiques", "value": "critical"},
                                             {"label": " Mode dégradé",      "value": "degraded"}],
                                    value=["critical"],
                                    className="custom-checklist"),
                            ], style={"flex": "1"}),
                        ], style={"display": "flex", "gap": "24px"}),
                    ], className="card"),
                ], style={"flex": "3"}),

                # ── PROFIL ───────────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("Compte Utilisateur", className="card-title"),
                        *[html.Div([
                            html.Div(label, className="filter-label"),
                            dcc.Input(value=val, type=typ, id=f"profile-{fid}",
                                      className="custom-input",
                                      style={"width": "100%", "marginBottom": "16px"}),
                        ]) for label, val, typ, fid in [
                            ("Nom utilisateur", "oumaima_engineer", "text", "name"),
                            ("Email", "oumaima@gtaplatform.ma", "email", "email"),
                            ("Mot de passe", "", "password", "password"),
                        ]],
                        html.Button("💾 Sauvegarder", id="btn-save-profile",
                                    className="btn btn-primary", style={"width": "100%"}),
                    ], className="card", style={"marginBottom": "16px"}),

                    html.Div([
                        html.Div("Sécurité", className="card-title"),
                        html.A("⬇ Exporter l'Audit Log",
                               href=f"{BACKEND}/data/export/csv",
                               className="btn btn-warn",
                               style={"display": "block", "textAlign": "center", "textDecoration": "none",
                                      "marginBottom": "10px"}),
                        html.Button("🔒 Déconnexion Sécurisée", id="btn-logout",
                                    className="btn btn-danger", style={"width": "100%"}),
                    ], className="card"),

                ], style={"flex": "1"}),

            ], style={"display": "flex", "gap": "16px"}),

        ], className="page-content"),
    ], className="main-content")