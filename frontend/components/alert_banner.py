"""
components/alert_banner.py — Panneau d'alertes hiérarchisé
"""
from dash import html

# ── Traduction des noms techniques → français ──────────────────────────────

_LABEL_FR = {
    # Vapeur HP
    "pressure_hp":          ("Pression HP",           "bar"),
    "temperature_hp":       ("Température HP",         "°C"),
    "steam_flow_hp":        ("Débit vapeur HP",        "T/h"),
    # Vapeur BP / condenseur
    "pressure_bp_in":       ("Pression BP entrée",     "bar"),
    "pressure_bp_barillet": ("Pression barillet BP",   "bar"),
    "temperature_bp":       ("Température BP",         "°C"),
    "steam_flow_condenser": ("Débit condenseur",       "T/h"),
    "pressure_condenser":   ("Pression condenseur",    "bar"),
    "condenser_level_pct":  ("Niveau hotwell",         "%"),
    "condenser_vacuum_mbar":("Vide condenseur",        "mbar"),
    # Mécanique
    "turbine_speed":        ("Vitesse arbre",          "RPM"),
    "speed_rpm":            ("Vitesse arbre",          "RPM"),
    "vib_bearing_fwd":      ("Vibration palier AV",    "mm/s"),
    "vib_bearing_aft":      ("Vibration palier AR",    "mm/s"),
    "temp_bearing_fwd":     ("Temp. palier AV",        "°C"),
    "temp_bearing_aft":     ("Temp. palier AR",        "°C"),
    "axial_displacement":   ("Déplacement axial",      "mm"),
    "casing_expansion":     ("Dilatation corps",       "mm"),
    # Lubrification
    "lube_oil_press":       ("Pression huile",         "bar"),
    "lube_oil_temp":        ("Temp. huile entrée",     "°C"),
    "lube_oil_temp_out":    ("Temp. huile sortie",     "°C"),
    "lube_oil_tank_level":  ("Niveau réservoir huile", "%"),
    "lube_oil_filter_dp":   ("ΔP filtre huile",        "bar"),
    # Électrique
    "active_power":         ("Puissance active",       "MW"),
    "reactive_power":       ("Puissance réactive",     "MVAR"),
    "apparent_power":       ("Puissance apparente",    "MVA"),
    "voltage":              ("Tension borne",          "kV"),
    "current_a":            ("Courant stator",         "A"),
    "power_factor":         ("Facteur de puissance",   ""),
    "frequency_hz":         ("Fréquence réseau",       "Hz"),
    "grid_frequency":       ("Fréquence réseau",       "Hz"),
    "efficiency":           ("Rendement",              "%"),
    # AVR
    "avr_e_fd_pu":          ("Excitation E_fd",        "p.u."),
}


def _format_msg(alert: dict) -> str:
    param = alert.get("parameter", "?")
    label, unit = _LABEL_FR.get(param, (param.replace("_", " ").capitalize(), ""))
    value     = alert.get("value", 0.0)
    threshold = alert.get("threshold", 0.0)
    unit_str  = f" {unit}" if unit else ""
    return f"{label} : {value:.1f}{unit_str} (limite {threshold:.1f}{unit_str})"


def alert_item(a):
    sev = a.get("severity", "INFO").upper()
    css = {"CRITICAL": "critical", "WARNING": "warning", "INFO": "info"}.get(sev, "info")
    icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(sev, "⚪")
    ts = a.get("timestamp", "")[:19].replace("T", " ")
    alert_id = a.get("id")
    is_ack = a.get("acknowledged", False)

    msg = _format_msg(a)
    content = [
        html.Span(icon, className="alert-icon"),
        html.Div([
            html.Span(msg, style={"fontWeight": "700"}),
        ], style={"flex": "1"}),
        html.Span(ts, style={"opacity": "0.5", "fontSize": "10px",
                             "whiteSpace": "nowrap", "marginRight": "10px"}),
    ]

    if not is_ack and alert_id is not None:
        content.append(
            html.Button(
                "Acquitter",
                id={"type": "ack-btn", "index": alert_id},
                className="btn-ack",
                style={
                    "cursor": "pointer", "fontSize": "10px", "padding": "2px 5px",
                    "borderRadius": "4px", "border": "1px solid white",
                    "backgroundColor": "transparent", "color": "inherit",
                },
            )
        )

    return html.Div(content, className=f"alert-banner {css}")


def _severity_badge(label, count, color, pulse_class=""):
    return html.Div([
        html.Span("●", style={"color": color, "fontSize": "14px", "marginRight": "5px"}),
        html.Span(f"{count}", style={"fontWeight": "700", "fontSize": "15px", "color": color}),
        html.Span(f" {label}", style={
            "fontSize": "10px", "color": "#94a3b8",
            "fontFamily": "Share Tech Mono", "marginLeft": "3px",
        }),
    ], className=pulse_class, style={
        "display": "flex", "alignItems": "center",
        "padding": "5px 10px",
        "background": "rgba(15,39,68,0.6)",
        "borderRadius": "6px",
        "border": f"1px solid {color}44",
    })


def _section(label, color, items):
    if not items:
        return None
    is_open = color == "#ef4444"
    return html.Details([
        html.Summary(f"{label}  ({len(items)})", style={
            "fontSize": "11px", "fontFamily": "Share Tech Mono",
            "color": color, "fontWeight": "700", "cursor": "pointer",
            "letterSpacing": "1px", "padding": "6px 0",
            "userSelect": "none",
        }),
        html.Div(
            [alert_item(a) for a in items],
            style={"maxHeight": "220px", "overflowY": "auto", "paddingRight": "4px"},
        ),
    ], open=is_open, className="alert-section")


def alerts_panel(alerts):
    if not alerts:
        return html.Div(
            "✅  Aucune alerte active — système nominal",
            style={"color": "#00e676", "fontFamily": "Share Tech Mono",
                   "fontSize": "12px", "padding": "10px"},
        )

    critical = [a for a in alerts if a.get("severity", "").upper() == "CRITICAL"]
    warning  = [a for a in alerts if a.get("severity", "").upper() == "WARNING"]
    info     = [a for a in alerts if a.get("severity", "").upper() == "INFO"]
    n_crit   = len(critical)

    header = html.Div([
        _severity_badge("Critique",      n_crit,       "#ef4444", "alert-pulse-red" if n_crit > 0 else ""),
        _severity_badge("Avertissement", len(warning), "#f59e0b"),
        _severity_badge("Info",          len(info),    "#60a5fa"),
    ], style={"display": "flex", "gap": "8px", "marginBottom": "12px", "flexWrap": "wrap"})

    sections = [s for s in [
        _section("🔴 ALARMES CRITIQUES", "#ef4444", critical),
        _section("⚠  AVERTISSEMENTS",   "#f59e0b", warning),
        _section("ℹ  INFORMATIONS",      "#60a5fa", info),
    ] if s is not None]

    return html.Div([header] + sections)
