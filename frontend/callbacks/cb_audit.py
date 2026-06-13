"""
callbacks/cb_audit.py — Journal opérateur (audit trail)
"""
import json
import requests
from dash import Input, Output, State, html, no_update
from config import BACKEND

_session = requests.Session()

_AUTO_USERS = ("AUTO", "SYSTÈME")

_ACTION_LABELS = {
    "VALVE_COMMAND":       "🔧 Commande vanne",
    "SCENARIO_TRIGGER":    "⚡ Déclenchement scénario",
    "SCENARIO_STOP":       "⏹ Arrêt scénario",
    "RESET":               "🔄 Réinitialisation système",
    "THRESHOLD_UPDATE":    "📏 Modification seuils",
    "ALERT_ACK":           "✅ Acquittement alarme",
    "SIM_RESET":           "🔄 Reset simulation",
    "SIM_ESV":             "🔧 ESV (simulation)",
    "SIM_SANDBOX":         "🧪 Bac à sable",
    "SIM_LUBE_OFFSET":     "🛢 Offset lubrification",
    "SIM_CONTROLS_RESET":  "🔄 Reset commandes simulation",
    "PROTECTION_INHIBIT":  "🛡 Inhibition protection",
    "MODE_CHANGE":         "🔁 Changement de mode",
    "SETPOINT_CHANGE":     "🎯 Changement de consigne",
    "PID_TUNE":            "📐 Réglage PID",
    "EMERGENCY_TRIP":      "🛑 Arrêt d'urgence (AU)",
    "TRIP_RESET":          "♻ Réinitialisation trip",
    "SETTING_CHANGE":      "⚙ Modification paramètre",
    "GRID_DISCONNECT":     "🔌 Découplage réseau",
    "SEQUENCE_START":      "▶ Démarrage séquence",
    "SEQUENCE_CANCEL":     "⏹ Annulation séquence",
    "SEQUENCE_END":        "🏁 Fin de séquence",
    "SEQUENCE_COMPLETED":  "🏁 Fin de séquence",
    "STARTUP_PHASE":       "🚀 Étape de démarrage",
    "STATE_TRANSITION":    "🔄 Changement d'état machine",
    "AVR_MODE_CHANGE":     "⚡ Mode AVR",
    "AVR_SETPOINT_CHANGE": "⚡ Consigne AVR",
    "AVR_GAINS_CHANGE":    "⚡ Gains AVR",
    "AVR_EFD_MANUAL":      "⚡ Excitation manuelle",
    "DEGRADATION_RESET":   "🔧 Reset usure machine",
    "ATTEMP_SETPOINT_CHANGE": "🌡 Consigne désurchauffeur",
    "ATTEMP_ENABLE":       "🌡 Activation désurchauffeur",
    "COND_LEVEL_SP_CHANGE":  "💧 Consigne niveau condenseur",
    "COND_VACUUM_SP_CHANGE": "💨 Consigne vide condenseur",
}

_TYPE_COLORS = {
    "VALVE_COMMAND":       "#38bdf8",
    "SCENARIO_TRIGGER":    "#f59e0b",
    "SCENARIO_STOP":       "#94a3b8",
    "RESET":               "#10b981",
    "THRESHOLD_UPDATE":    "#c084fc",
    "ALERT_ACK":           "#34d399",
    "SIM_RESET":           "#10b981",
    "SIM_ESV":             "#38bdf8",
    "SIM_SANDBOX":         "#a78bfa",
    "SIM_LUBE_OFFSET":     "#a78bfa",
    "SIM_CONTROLS_RESET":  "#10b981",
    "PROTECTION_INHIBIT":  "#f87171",
    "MODE_CHANGE":         "#c084fc",
    "SETPOINT_CHANGE":     "#c084fc",
    "PID_TUNE":            "#c084fc",
    "EMERGENCY_TRIP":      "#ef4444",
    "TRIP_RESET":          "#10b981",
    "SETTING_CHANGE":      "#94a3b8",
    "GRID_DISCONNECT":     "#fb923c",
    "SEQUENCE_START":      "#facc15",
    "SEQUENCE_CANCEL":     "#94a3b8",
    "SEQUENCE_END":        "#facc15",
    "SEQUENCE_COMPLETED":  "#facc15",
    "STARTUP_PHASE":       "#facc15",
    "STATE_TRANSITION":    "#fbbf24",
    "AVR_MODE_CHANGE":     "#fb923c",
    "AVR_SETPOINT_CHANGE": "#fb923c",
    "AVR_GAINS_CHANGE":    "#fb923c",
    "AVR_EFD_MANUAL":      "#fb923c",
    "DEGRADATION_RESET":   "#94a3b8",
    "ATTEMP_SETPOINT_CHANGE": "#2dd4bf",
    "ATTEMP_ENABLE":       "#2dd4bf",
    "COND_LEVEL_SP_CHANGE":  "#22d3ee",
    "COND_VACUUM_SP_CHANGE": "#22d3ee",
}

# Libellés lisibles pour les "cibles" techniques
_TARGET_LABELS = {
    "mode":               "Mode de fonctionnement",
    "setpoints":          "Consignes",
    "trip":               "Sécurité (trip)",
    "v1":                 "Vanne V1 (admission HP)",
    "grid":               "Couplage réseau",
    "machine_state":      "État de la machine",
    "esv":                "ESV (vanne d'arrêt)",
    "bp_admit":           "Admission vapeur barrage",
    "avr":                "Excitation (AVR)",
    "barrage_warmup_s":   "Durée préchauffage barrage",
    "vannes":             "Vannes V1/V2/V3/BP",
    "V1,V2,V3,BP":        "Vannes V1/V2/V3/BP",
    "ALL":                "Système complet",
    "sim_machine":        "Machine simulée",
    "esv_sim":            "ESV (simulation)",
    "sandbox_sim":        "Bac à sable (simulation)",
    "lube_sim":           "Lubrification (simulation)",
    "esv_avr_lube_sim":   "ESV / AVR / Lubrification (simulation)",
    "avr_mode":           "Mode AVR",
    "avr_setpoint":       "Consigne AVR",
    "avr_gains":          "Gains AVR",
    "avr_e_fd_manual":    "Excitation manuelle (E_fd)",
    "attemp_t_hp_setpoint": "Consigne température HP (désurchauffeur)",
    "attemp_enabled":     "Activation désurchauffeur",
    "cond_level_sp":      "Consigne niveau condenseur",
    "cond_vacuum_sp":     "Consigne vide condenseur",
}

# Libellés lisibles pour les états / phases machine
_PHASE_LABELS = {
    "PRE_CHECKS":      "Vérifications préalables",
    "BARRAGE_OPENED":  "Vapeur barrage ouverte",
    "ESV_OPENED":      "ESV ouverte",
    "V1_OPENING":      "Ouverture V1",
    "ACCELERATING":    "Accélération",
    "READY_TO_EXCITE": "Prêt à exciter",
    "EXCITED":         "Excitation active",
    "SYNCHRONIZING":   "Synchronisation",
    "GRID_CONNECTED":  "Couplé au réseau",
    "STOPPED":         "Arrêtée",
    "ROLLING":         "Lancement (rolling)",
    "TRIPPED":         "Déclenchée (trip)",
}

_SETPOINT_LABELS = {
    "power_mw":  "Puissance",
    "speed_rpm": "Vitesse",
}


def _try_json_dict(s):
    """Renvoie un dict si `s` est une chaîne JSON représentant un objet, sinon None."""
    if not s or not isinstance(s, str):
        return None
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except (ValueError, TypeError):
        return None


def _ph(v):
    return _PHASE_LABELS.get(v, v)


def _describe(row) -> str:
    """Construit une description en langage clair pour l'opérateur."""
    a       = row.get("action_type", "")
    target  = row.get("target") or ""
    before  = row.get("value_before")
    after   = row.get("value_after")
    bd, ad  = _try_json_dict(before), _try_json_dict(after)

    if a == "VALVE_COMMAND":
        if bd and ad:
            parts = [f"{k.upper()} : {bd.get(k, '?')}% → {v}%"
                     for k, v in ad.items() if bd.get(k) != v]
            return "Vannes — " + (", ".join(parts) if parts else "aucun changement")
        return f"Vannes : {before} → {after}"

    if a == "MODE_CHANGE":
        return f"Mode de fonctionnement : {before} → {after}"

    if a == "SETPOINT_CHANGE":
        if bd and ad:
            parts = [f"{_SETPOINT_LABELS.get(k, k)} : {bd.get(k)} → {v}"
                     for k, v in ad.items() if bd.get(k) != v]
            return ", ".join(parts) if parts else "Consignes inchangées"
        return f"Consignes : {before} → {after}"

    if a == "PID_TUNE":
        loop = target.replace("pid_", "").replace("_gains", "")
        if bd and ad:
            parts = [f"{k.upper()} : {bd.get(k)} → {v}"
                     for k, v in ad.items() if bd.get(k) != v]
            return f"PID {loop} — " + (", ".join(parts) if parts else "inchangé")
        return f"PID {loop} : {before} → {after}"

    if a == "EMERGENCY_TRIP":
        return "Arrêt d'urgence déclenché — V1 fermée instantanément, machine en TRIP"

    if a == "TRIP_RESET":
        return "Trip réinitialisé — machine prête pour redémarrage (ARRÊTÉE)"

    if a == "GRID_DISCONNECT":
        return "Découplage du réseau — ESV/V1/V2/V3 fermées, ralentissement (coast-down)"

    if a == "STATE_TRANSITION":
        return f"État machine : {_ph(before)} → {_ph(after)}"

    if a == "STARTUP_PHASE":
        return f"Phase de démarrage : {_ph(before)} → {_ph(after)}"

    if a == "SEQUENCE_START":
        return f"Séquence « {target} » démarrée — puissance {before} MW → {after} MW visé"

    if a == "SEQUENCE_CANCEL":
        return f"Séquence « {target} » annulée"

    if a in ("SEQUENCE_END", "SEQUENCE_COMPLETED"):
        return f"Séquence « {target} » terminée"

    if a == "SCENARIO_TRIGGER":
        return f"Scénario « {after} » déclenché"

    if a == "SCENARIO_STOP":
        return f"Scénario « {before} » arrêté"

    if a == "THRESHOLD_UPDATE":
        if bd and ad:
            parts = [f"{k} : {bd.get(k)} → {v}" for k, v in ad.items()]
            return "Seuils modifiés — " + ", ".join(parts)
        return f"Seuils modifiés : {target}"

    if a == "ALERT_ACK":
        return f"Alarme {target.replace('alert_', '#')} acquittée"

    if a == "AVR_MODE_CHANGE":
        return f"Mode AVR : {before} → {after}"

    if a == "AVR_SETPOINT_CHANGE":
        return f"Consigne AVR : {before} → {after}"

    if a == "AVR_GAINS_CHANGE":
        return f"Gains AVR : {before} → {after}"

    if a == "AVR_EFD_MANUAL":
        return f"Excitation manuelle E_fd : {before} → {after}"

    if a == "ATTEMP_SETPOINT_CHANGE":
        return f"Consigne température HP (désurchauffeur) : {before} °C → {after} °C"

    if a == "ATTEMP_ENABLE":
        return f"Désurchauffeur : {'activé' if after == 'True' else 'désactivé'}"

    if a == "COND_LEVEL_SP_CHANGE":
        return f"Consigne niveau condenseur : {before}% → {after}%"

    if a == "COND_VACUUM_SP_CHANGE":
        return f"Consigne vide condenseur : {before} → {after} mbar"

    if a == "DEGRADATION_RESET":
        return f"Compteur d'usure réinitialisé ({before} h → 0 h)"

    if a == "PROTECTION_INHIBIT":
        return f"Protection « {target} » {'inhibée' if after == 'True' else 'réactivée'}"

    if a == "SETTING_CHANGE":
        return f"{_TARGET_LABELS.get(target, target)} : {before} → {after}"

    if a == "RESET":
        return "Réinitialisation complète du système → retour à l'état nominal"

    if a == "SIM_RESET":
        return "Machine simulée resynchronisée avec la machine réelle"

    if a == "SIM_ESV":
        return f"ESV (simulation) : {'ouverte' if after == 'True' else 'fermée'}"

    if a == "SIM_SANDBOX":
        return f"Bac à sable simulation : {'activé' if after == 'True' else 'désactivé'}"

    if a == "SIM_LUBE_OFFSET":
        return f"Offsets lubrification (simulation) appliqués : {after}"

    if a == "SIM_CONTROLS_RESET":
        return "Commandes simulation (ESV/AVR/lubrification) réinitialisées au nominal"

    # Repli générique
    tgt = _TARGET_LABELS.get(target, target)
    if before is not None or after is not None:
        return f"{tgt} : {before} → {after}" if tgt else f"{before} → {after}"
    return tgt or "—"


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
        for col in ["Horodatage", "Acteur", "Action", "Description", "Notes"]
    ])

    data_rows = []
    for i, row in enumerate(rows):
        user  = row.get("user", "—")
        atype = row.get("action_type", "")
        bg    = "rgba(255,255,255,0.02)" if i % 2 == 0 else "transparent"

        is_auto = user in _AUTO_USERS
        actor   = ("🤖 Automate" if is_auto else f"👤 {user}")
        actor_color = "#94a3b8" if is_auto else "#e2e8f0"

        raw_tooltip = (f"action={atype} | cible={row.get('target')} | "
                       f"avant={row.get('value_before')} | après={row.get('value_after')}")

        def cell(val, color=None, mono=False, wrap=False, title=None):
            style = {
                "padding": "7px 12px",
                "fontSize": "11px",
                "fontFamily": "var(--mono)" if mono else "var(--ui)",
                "color": color or "var(--text)",
                "borderBottom": "1px solid rgba(255,255,255,0.04)",
            }
            if wrap:
                style.update({"maxWidth": "420px", "whiteSpace": "normal",
                               "lineHeight": "1.5"})
            else:
                style.update({"maxWidth": "180px", "overflow": "hidden",
                               "textOverflow": "ellipsis", "whiteSpace": "nowrap"})
            return html.Td(str(val) if val is not None else "—", style=style,
                            title=title if title is not None else (str(val) if val else ""))

        data_rows.append(html.Tr([
            cell(row.get("ts", "")[:19], mono=True),
            cell(actor, color=actor_color),
            cell(_ACTION_LABELS.get(atype, atype), color=_TYPE_COLORS.get(atype, "#94a3b8")),
            cell(_describe(row), wrap=True, title=raw_tooltip),
            cell(row.get("notes"), color="#f59e0b", wrap=True),
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
    def refresh_journal(_, _btn, pathname, ftype, factor, limit):
        if pathname != "/journal":
            return no_update, no_update, no_update

        params = {"limit": limit or 100}
        try:
            r = _session.get(f"{BACKEND}/audit/operator-actions", params=params, timeout=3)
            rows = r.json() if r.status_code == 200 else []
        except Exception:
            rows = []

        # Filtres locaux (type d'action et acteur)
        if ftype and ftype != "ALL":
            rows = [r for r in rows if r.get("action_type") == ftype]
        if factor and factor != "ALL":
            if factor == "AUTO":
                rows = [r for r in rows if r.get("user") in _AUTO_USERS]
            elif factor == "OPERATOR":
                rows = [r for r in rows if r.get("user") not in _AUTO_USERS]

        table  = _make_table(rows)
        count  = f"{len(rows)} action(s) affichée(s)"
        export = f"{BACKEND}/audit/operator-actions/export/csv"
        return table, count, export
