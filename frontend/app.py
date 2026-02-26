import os

"""
app.py — Point d'entrée principal du frontend Dash
Digital Twin GTA — Interface de Supervision Industrielle
Optimisé :
  - debug/hot_reload via variable ENV (désactivé en prod)
  - Intervalles AI et Analysis déplacés ici (global, non dupliqués)
  - Compression via Flask middleware
"""

import os
import dash
from dash import Dash, html, dcc, Input, Output, State
from flask_compress import Compress

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

# ── Layout racine (routing multi-pages) ────────────────────────────
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),

    # Stores Globaux (Source de vérité unique)
    dcc.Store(id="store-current-data",    data={}),
    dcc.Store(id="store-simulation-data", data={}),
    dcc.Store(id="store-history",         data=[]),

    # Intervalles globaux
    dcc.Interval(id="interval-fast", interval=1000, n_intervals=0),   # 1s  — données temps réel
    dcc.Interval(id="interval-slow", interval=5000, n_intervals=0),   # 5s  — alertes

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