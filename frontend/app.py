import os

"""
app.py — Point d'entrée principal du frontend Dash
Digital Twin GTA — Interface de Supervision Industrielle
Optimisé :
  - debug/hot_reload via variable ENV (désactivé en prod)
  - Intervalles AI et Analysis déplacés ici (global, non dupliqués)
  - Compression via Flask middleware
  - WebSocket (dash-extensions) pour push temps réel sans polling
"""

import dash
from dash import Dash, html, dcc, Input, Output, State
from flask_compress import Compress
from dash_extensions import WebSocket

# ── Import des layouts ──────────────────────────────────────────────
from layouts.dashboard  import layout as dashboard_layout
from layouts.simulation import layout as simulation_layout
from layouts.analysis   import layout as analysis_layout
from layouts.ai_module  import layout as ai_layout
from layouts.settings   import layout as settings_layout

# ── Import des callbacks ────────────────────────────────────────────
from callbacks import cb_dashboard, cb_simulation, cb_analysis, cb_ai, cb_settings, cb_data

# ── Mode debug (désactivé en production) ────────────────────────────
DEBUG = os.getenv("DASH_DEBUG", "false").lower() == "true"

# ── Initialisation Dash ─────────────────────────────────────────────
app = Dash(
    __name__,
    suppress_callback_exceptions=True,
    title="GTA Digital Twin",
    update_title=None,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": "Supervision Groupe Turbo-Alternateur GTA"},
    ],
)

server = app.server  # Pour déploiement WSGI / Docker

# ── Compression GZIP des réponses HTTP ──────────────────────────────
Compress(server)

# ── URL WebSocket (dérivée de PUBLIC_BACKEND_URL pour le navigateur) ─
from config import PUBLIC_BACKEND
_WS_URL = PUBLIC_BACKEND.replace("http://", "ws://").replace("https://", "wss://") + "/ws/data"

# ── Layout racine (routing multi-pages) ────────────────────────────
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),

    # WebSocket — push instantané toutes les 500ms depuis le backend
    WebSocket(id="ws-data", url=_WS_URL),

    # Stores Globaux (Source de vérité unique)
    dcc.Store(id="store-current-data",    data={}),
    dcc.Store(id="store-simulation-data", data={}),
    dcc.Store(id="store-history",         data=[]),
    # Output factice du clientside_callback synoptique [FIX-5c]
    # Le callback JS patche le SVG en place — ce store n'est jamais lu
    dcc.Store(id="syn-patch-tick",        data=0),

    # Valeur = clé dans _SPARK_PARAMS (ex: "active_power", "pressure_hp"…)
    dcc.Store(id="store-spark-param",     data=None),
 
    # NOUVEAU : mode Analyse ("live" = temps réel WS, "history" = HTTP historique)
    dcc.Store(id="analysis-mode",         data="history"),

    # Ajouter dans app.layout, avec les autres dcc.Store
    dcc.Store(id="store-dash-panel-tab", data=0),

    # Intervalles (uniquement pour horloge et alertes, données viennent du WS)
    dcc.Interval(id="interval-fast", interval=1000, n_intervals=0, disabled=True),   # 1s  — horloge
    dcc.Interval(id="interval-slow", interval=5000, n_intervals=0),   # 5s  — alertes

    # Activé uniquement sur /  (géré dans cb_dashboard)
    dcc.Interval(id="interval-spark-poll", interval=300, n_intervals=0, disabled=True),

    html.Div(id="page-content"),
])

# ── Routing ────────────────────────────────────────────────────────
@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
)
def display_page(pathname):
    routes = {
        "/":           dashboard_layout,
        "/simulation": simulation_layout,
        "/analysis":   analysis_layout,
        "/ai":         ai_layout,
        "/settings":   settings_layout,
    }
    layout_fn = routes.get(pathname, dashboard_layout)
    return layout_fn()

# ── Enregistrement des callbacks ────────────────────────────────────
cb_data.register(app)
cb_dashboard.register(app)
cb_simulation.register(app)
cb_analysis.register(app)
cb_ai.register(app)
cb_settings.register(app)

# ── Lancement ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("""
    ===========================================================
    GTA Digital Twin — Interface de Supervision
    http://localhost:8050
    ===========================================================
    """)
    app.run(
        host="0.0.0.0",
        port=8050,
        debug=DEBUG,
        dev_tools_hot_reload=DEBUG,
    )