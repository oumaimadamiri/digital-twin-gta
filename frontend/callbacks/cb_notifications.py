"""
callbacks/cb_notifications.py — Notifications globales (toasts) pour alarmes critiques
"""
import requests
from dash import Input, Output, no_update, clientside_callback
from config import BACKEND

_session = requests.Session()

_seen_ids = set()
_initialized = [False]


def register(app):

    @app.callback(
        Output("global-toast-store", "data"),
        Input("interval-slow", "n_intervals"),
    )
    def poll_critical_alerts(_n):
        try:
            alerts = _session.get(
                f"{BACKEND}/settings/alerts?limit=10&only_active=true", timeout=2
            ).json()
        except Exception:
            return no_update

        critical = [a for a in alerts if a.get("severity") == "CRITICAL"]

        # Au premier appel : mémorise les alarmes déjà actives sans notifier
        if not _initialized[0]:
            _seen_ids.update(a.get("id") for a in critical)
            _initialized[0] = True
            return no_update

        new_alerts = [a for a in critical if a.get("id") not in _seen_ids]
        if not new_alerts:
            return no_update

        for a in new_alerts:
            _seen_ids.add(a.get("id"))

        latest = new_alerts[0]
        return {
            "title":   "Alarme critique",
            "message": latest.get("message", ""),
            "n":       latest.get("id"),
        }
    # ── Affichage toast (DOM direct, auto-dismiss) ──────────────────────
    clientside_callback(
        """
        function(data) {
            if (!data) return window.dash_clientside.no_update;
            var container = document.getElementById('global-toast-container');
            if (!container) return window.dash_clientside.no_update;

            var toast = document.createElement('div');
            toast.className = 'app-toast app-toast-critical';
            toast.innerHTML =
                '<span class="app-toast-icon">\\uD83D\\uDD34</span>' +
                '<div class="app-toast-body">' +
                  '<div class="app-toast-title">' + (data.title || '') + '</div>' +
                  '<div class="app-toast-message">' + (data.message || '') + '</div>' +
                '</div>' +
                '<span class="app-toast-close">\\u2715</span>';

            toast.querySelector('.app-toast-close').onclick = function() {
                toast.remove();
            };

            container.appendChild(toast);
            setTimeout(function() { toast.remove(); }, 8000);

            return '';
        }
        """,
        Output("global-toast-dummy", "children"),
        Input("global-toast-store", "data"),
        prevent_initial_call=True,
    )