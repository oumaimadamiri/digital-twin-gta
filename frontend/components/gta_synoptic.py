from dash import html
import dash_dangerously_set_inner_html


STATUS_COLORS = {
    "NORMAL":   {"stroke": "#10b981", "glow": "rgba(16,185,129,0.25)", "label": "#10b981"},
    "DEGRADED": {"stroke": "#f59e0b", "glow": "rgba(245,158,11,0.25)",  "label": "#f59e0b"},
    "CRITICAL": {"stroke": "#ef4444", "glow": "rgba(239,68,68,0.3)",    "label": "#ef4444"},
    "TRIPPED":  {"stroke": "#ef4444", "glow": "rgba(239,68,68,0.45)",   "label": "#fca5a5"},
}

_DEFAULTS = {
    # État initial : machine en GRID_CONNECTED (cohérent avec boot)
    "status":               "NORMAL",
    # Source vapeur HP
    "pressure_hp":          60.0,
    "temperature_hp":       440.0,
    "steam_flow_hp":        120.0,
    # BP
    "pressure_bp_in":       4.4,
    "temperature_bp":       145.0,
    "pressure_bp_barillet": 4.4,
    "steam_flow_condenser": 87.0,
    "pressure_condenser":   0.08,   # vide établi
    # Turbine
    "turbine_speed":        6435.0,
    "efficiency":           58.0,
    # Électrique — valeurs nominales GRID_CONNECTED
    "active_power":         24.0,
    "power_factor":         0.85,
    "reactive_power":       14.0,
    "apparent_power":       28.2,
    "voltage":              10.5,
    "current_a":            1551.0,
    # Vannes — posture régime permanent
    "valve_v1":             100.0,
    "valve_v2":             100.0,
    "valve_v3":             100.0,
    "valve_bp":             80.0,
    # Centrale Huile Lubrification
    "lube_oil_press":       1.5,
    "lube_oil_temp":        45.0,
    "lube_oil_temp_out":    60.0,
    "lube_oil_tank_level":  80.0,
    "lube_oil_pump":        "MAIN",
    "lube_oil_filter_dp":   0.3,
}


def _vc(pct, hi_col="#f97316", lo_col="#ef4444"):
    if pct >= 75: return hi_col
    if pct >= 30: return "#f59e0b"
    return lo_col


def _alarm(val, lo, hi):
    return val < lo or val > hi


def _tag_static(x, y, label, elem_id, default_value, default_unit,
                alarm=False, anchor="middle", w=90, param_name=None):
    """
    Génère un tag SCADA avec id stable pour patch JS.

    NOUVEAU : param_name (optionnel) — si fourni, le tag devient cliquable.
    onclick → pose window._svgClickParam = param_name
    → détecté par interval-spark-poll → met à jour store-spark-param → sparkline Dashboard.
    """
    val_color  = "#ef4444" if alarm else "#e2e8f0"
    bkg        = "rgba(239,68,68,0.12)" if alarm else "rgba(15,23,42,0.75)"
    border     = "#ef4444" if alarm else "#1e3a5f"
    xi  = x - w//2 if anchor == "middle" else x
    xt  = x if anchor == "middle" else x + w//2

    # Attributs du groupe cliquable
    if param_name:
        click_attrs = (
            f' onclick="window._svgClickParam=\'{param_name}\'"'
            f' style="cursor:pointer"'
            f' title="Afficher la tendance : {label}"'
        )
        # Halo de survol via CSS (classe hover-tag)
        extra_class = "hover-tag"
    else:
        click_attrs = ""
        extra_class = ""

    return f"""
    <g id="{elem_id}-g" class="{'blink' if alarm else ''} {extra_class}"{click_attrs}>
      <rect id="{elem_id}-rect" x="{xi}" y="{y}" width="{w}" height="34"
            rx="4" fill="{bkg}" stroke="{border}" stroke-width="0.8"/>
      <text x="{xt}" y="{y+11}"
            fill="#64748b" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{label}</text>
      <text id="{elem_id}-val" x="{xt}" y="{y+25}"
            fill="{val_color}" font-size="12" font-weight="700" text-anchor="middle"
            font-family="Share Tech Mono">{default_value} <tspan id="{elem_id}-unit" fill="#64748b" font-size="9" font-weight="400">{default_unit}</tspan></text>
    </g>"""


def _valve_symbol_static(cx, cy, pct, target, name, col, vid, size=18, orient="top"):
    if orient == "right":
        actuator = f"""
        <line x1="{cx+size}" y1="{cy}" x2="{cx+size+10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx+size+10} {cy-size+2} Q {cx+size+18} {cy} {cx+size+10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text id="{vid}-tgt" x="{cx+size+22}" y="{cy-8}" fill="#94a3b8" font-size="9" text-anchor="start" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    elif orient == "left":
        actuator = f"""
        <line x1="{cx-size}" y1="{cy}" x2="{cx-size-10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size-10} {cy-size+2} Q {cx-size-18} {cy} {cx-size-10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text id="{vid}-tgt" x="{cx-size-22}" y="{cy-8}" fill="#94a3b8" font-size="9" text-anchor="end" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    else:
        actuator = f"""
        <line x1="{cx}" y1="{cy-size}" x2="{cx}" y2="{cy-size-5}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size+2} {cy-size-5} Q {cx} {cy-size-12} {cx+size-2} {cy-size-5} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text id="{vid}-tgt" x="{cx}" y="{cy-size-12}" fill="#94a3b8" font-size="9" text-anchor="middle" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'

    return f"""
    {tgt_txt}
    {actuator}
    <circle id="{vid}-circle" cx="{cx}" cy="{cy}" r="{size}" fill="#0a101a" stroke="{col}" stroke-width="2"/>
    <text x="{cx}" y="{cy-1}" fill="{col}" font-size="9" font-weight="700" text-anchor="middle" font-family="Share Tech Mono">{name}</text>
    <text id="{vid}-pct" x="{cx}" y="{cy+9}" fill="{col}" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{pct:.0f}%</text>"""


def _group_tag_static(cx, cy, label, elem_id, param_name, color, w=85):
    """Bouton launcher compact (dashed border) pour un groupe de paramètres."""
    xi = cx - w // 2
    if param_name:
        interact = f'onclick="window._svgClickParam=\'{param_name}\'" style="cursor:pointer" title="Voir les tendances : {label}"'
        cls = "hover-tag"
    else:
        interact = ""
        cls = ""
    return f"""
    <g id="{elem_id}" class="{cls}" {interact}>
      <rect x="{xi}" y="{cy}" width="{w}" height="20" rx="10"
            fill="rgba(59,130,246,0.06)" stroke="{color}"
            stroke-width="0.8" stroke-dasharray="4,2"/>
      <text x="{cx}" y="{cy+13}" fill="{color}" font-size="8.5" font-weight="700"
            text-anchor="middle" font-family="Share Tech Mono">{label}</text>
    </g>"""


def _instrument_circle(cx, cy, label, col="#60a5fa", r=11):
    return f"""
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="#0a101a" stroke="{col}" stroke-width="1.2"/>
    <text x="{cx}" y="{cy+4}" fill="{col}" font-size="8" font-weight="600"
          text-anchor="middle" font-family="Share Tech Mono">{label}</text>"""


# ─────────────────────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────────────────────

def create_gta_synoptic_static(show_table: bool = True, interactive: bool = True) -> html.Div:
    return _build_synoptic_div(_DEFAULTS, static_ids=True, show_table=show_table, interactive=interactive)


def create_gta_synoptic(data: dict) -> html.Div:
    merged = {**_DEFAULTS, **{k: v for k, v in data.items() if v is not None}}
    return _build_synoptic_div(merged, static_ids=False)


def _build_synoptic_div(data: dict, static_ids: bool, show_table: bool = True, interactive: bool = True) -> html.Div:

    status  = data.get("status", "NORMAL")
    p_hp    = data.get("pressure_hp",      60.0)
    t_hp    = data.get("temperature_hp",  486.0)
    q_hp    = data.get("steam_flow_hp",   120.0)
    p_bp_in  = data.get("pressure_bp_in",       4.5)
    t_bp     = data.get("temperature_bp",      226.0)
    p_bar_bp = data.get("pressure_bp_barillet", 3.0)
    q_cond   = data.get("steam_flow_condenser",  74.0)
    p_cond   = data.get("pressure_condenser",  0.0064)
    speed   = data.get("turbine_speed",   6435.0)
    eff     = data.get("efficiency",        58.0)
    power   = data.get("active_power",      24.0)
    pf      = data.get("power_factor",       0.85)
    q_mvar  = data.get("reactive_power",    21.4)
    s_mva   = data.get("apparent_power",    41.0)
    voltage = data.get("voltage",           10.5)
    i_a     = data.get("current_a",        2254.0)
    v1      = data.get("valve_v1",  100.0)
    v1_tgt  = data.get("valve_v1_target", v1)
    v2      = data.get("valve_v2",  100.0)
    v2_tgt  = data.get("valve_v2_target", v2)
    v3      = data.get("valve_v3",  100.0)
    v3_tgt  = data.get("valve_v3_target", v3)
    v_bp    = data.get("valve_bp",   80.0)
    v_bp_tgt= data.get("valve_bp_target", v_bp)

    freq    = data.get("grid_frequency", 50.00)
    vib_fwd = data.get("vib_bearing_fwd", 2.1)
    vib_aft = data.get("vib_bearing_aft", 1.8)
    temp_fwd= data.get("temp_bearing_fwd", 74.0)
    temp_aft= data.get("temp_bearing_aft", 76.0)
    oil_p       = data.get("lube_oil_press",       1.5)
    oil_t       = data.get("lube_oil_temp",        45.0)
    oil_t_out   = data.get("lube_oil_temp_out",    60.0)
    oil_lvl     = data.get("lube_oil_tank_level",  80.0)
    oil_pump    = data.get("lube_oil_pump",        "MAIN")
    oil_dp      = data.get("lube_oil_filter_dp",   0.3)
    axial   = data.get("axial_displacement", 0.2)
    casing  = data.get("casing_expansion", 5.0)
    scenario = data.get("scenario")

    _q_hp_eff          = q_hp * (v1 / 100.0)
    _q_extract         = _q_hp_eff * 0.38
    flow_barillet_val_in    = round(_q_extract, 1)
    flow_chauffage_val   = round(_q_extract * 0.60, 1)
    flow_surchauffeur_val = round(_q_extract * 0.40, 1)

    alm_php  = _alarm(p_hp,  55, 65)
    alm_thp  = _alarm(t_hp, 420, 500)
    alm_qhp  = _alarm(q_hp, 100, 130)
    alm_spd  = _alarm(speed, 6300, 6550)
    alm_pow  = power > 30.0
    alm_pf   = _alarm(pf, 0.82, 0.86)
    alm_eff  = eff < 51.0 or eff > 65.0
    warn_eff = (not alm_eff) and (eff < 55.0 or eff > 61.0)
    alm_pbar_bp = p_bar_bp > 5.0
    alm_ia   = i_a > 3000

    sc       = STATUS_COLORS.get(status, STATUS_COLORS["NORMAL"])["stroke"]
    hp_col   = "#ef4444" if alm_thp else "#f97316"
    alt_col  = "#ef4444" if alm_pow else ("#f59e0b" if power > 24 else "#10b981")
    vc1      = _vc(v1,  "#f97316")
    vc2      = _vc(v2,  "#60a5fa")
    vc3      = _vc(v3,  "#60a5fa")
    vc_bp    = _vc(v_bp,"#3b82f6")
    bp_admit     = data.get("valve_bp_admit", 0.0)
    bp_admit_tgt = data.get("valve_bp_admit_target", 0.0)
    vc_bp_admit  = _vc(bp_admit, "#f59e0b")

    # ── Couleurs table État Système ──────────────────────────────────────────
    c_tbl_php  = "#ef4444" if alm_php else "#f97316"
    c_tbl_thp  = "#ef4444" if alm_thp else "#f97316"
    c_tbl_spd  = "#ef4444" if alm_spd else "#818cf8"
    c_tbl_eff  = "#ef4444" if alm_eff else "#f59e0b" if warn_eff else "#38bdf8"
    c_tbl_v1   = "#ef4444" if v1 < 30  else "#f97316"
    c_tbl_vbp  = "#ef4444" if v_bp < 30 else "#38bdf8"
    c_tbl_pbar = "#ef4444" if p_bar_bp > 5.0 else "#a78bfa"
    c_tbl_vib  = "#ef4444" if vib_fwd > 4.5 else "#fbbf24"
    c_tbl_oilt = "#ef4444" if oil_t > 60 else "#60a5fa"
    c_tbl_dot  = {"NORMAL": "#10b981", "DEGRADED": "#f59e0b", "CRITICAL": "#ef4444"}.get(status, "#10b981")
    tbl_pulse  = "pulse" if status != "NORMAL" else ""
    # Page 2 — couleurs initiales
    c_tbl2_pbpin  = "#38bdf8"
    c_tbl2_qcond  = "#7dd3fc"
    c_tbl2_pcond  = "#a78bfa"
    c_tbl2_freq   = "#ef4444" if abs(freq   - 50.0) > 0.5 else "#10b981"
    c_tbl2_vibaft = "#ef4444" if vib_aft   > 4.5   else "#fbbf24"
    c_tbl2_tfwd   = "#ef4444" if temp_fwd  > 85    else "#60a5fa"
    c_tbl2_taft   = "#ef4444" if temp_aft  > 85    else "#60a5fa"
    c_tbl2_oilp   = "#ef4444" if oil_p     < 0.8   else "#10b981"
    c_tbl2_axial  = "#ef4444" if abs(axial) > 1.0   else "#10b981"
    c_tbl2_casing = "#ef4444" if casing    > 8.0   else "#10b981"

    flow_dur = f"{max(0.3, 120.0/max(1, q_hp)):.2f}s" if q_hp > 5 else "99999s"
    rpm_norm = min(max(speed / 6435.0, 0), 1)
    rpm_curve = rpm_norm ** 0.7
    spin_dur = f"{max(0.3, 4.0 - rpm_curve*3.7):.2f}s"
    turb_cls = "vibrate" if speed > 6500 else ""

    def sid(name):
        return f' id="syn-{name}"' if static_ids else ""

    # ── Tags SCADA — param_name activé seulement sur Dashboard (interactive) ──
    if static_ids:
        _p = lambda name: name if interactive else None
        tag_php  = _tag_static(80,  251, "Pression",    "syn-php",  f"{p_hp:.1f}",  "bar",  alm_php,
                               param_name=_p("pressure_hp"))
        tag_thp  = _tag_static(80,  289, "Température", "syn-thp",  f"{t_hp:.0f}",  "°C",   alm_thp,
                               param_name=_p("temperature_hp"))
        tag_qhp  = _tag_static(185, 193, "Débit HP",    "syn-qhp",  f"{q_hp:.0f}",  "T/h",  alm_qhp,
                               w=55, param_name=_p("steam_flow_hp"))
        tag_spd  = _tag_static(755, 265, "Vit. arbre",  "syn-spd",  f"{speed:.0f}", "RPM",  alm_spd,
                               w=55, param_name=_p("turbine_speed"))
        tag_v1   = _tag_static(330, 273, "Adm. HP",     "syn-v1t",  f"{v1:.0f}",    "%",    False, w=60)
        tag_vit2 = _tag_static(915, 264, "Vit.",        "syn-vit2", "1500",          "RPM",  False, w=55)
        tag_turbine_int = _group_tag_static(
            435, 133, "⋯ Param Turbine", "syn-turbine-int-launcher",
            "__turbine_int__" if interactive else None, "#38bdf8", w=90)
        tag_alt_group   = _group_tag_static(
            1000, 157, "⋯ Param Alternateur", "syn-alt-launcher",
            "__alternateur__" if interactive else None, "#10b981", w=90)
        tag_turb_bottom = (
            _tag_static(450, 315, "Vit. arbre", "syn-bx-spd", f"{speed:.0f}",   "RPM",  alm_spd,       w=80 , param_name=_p("turbine_speed")) +
            _tag_static(555, 315, "Rendement",  "syn-bx-eff", f"{eff:.1f}",     "%",    alm_eff,       w=80 , param_name=_p("efficiency")) +
            _tag_static(660, 315, "Vib. Avant", "syn-bx-vib", f"{vib_fwd:.1f}", "mm/s", vib_fwd > 4.5, w=80)
        )
        tag_alt_bottom = (
            _tag_static(974,  295, "P active", "syn-bx-pout", f"{power:.1f}", "MW", alm_pow, w=48, param_name=_p("active_power")) +
            _tag_static(1027, 295, "cos φ",    "syn-bx-pf",   f"{pf:.3f}",   "",   alm_pf,  w=48, param_name=_p("power_factor")) +
            _tag_static(1080, 295, "Courant",  "syn-bx-ia",   f"{i_a:.0f}",  "A",  alm_ia,  w=48, param_name=_p("current_a"))
        )
    else:
        tag_php  = _tag(80,  251, "Pression",    f"{p_hp:.1f}",  "bar", alm_php)
        tag_thp  = _tag(80,  289, "Température", f"{t_hp:.0f}",  "°C",  alm_thp)
        tag_qhp  = _tag(185, 193, "Débit HP",    f"{q_hp:.0f}",  "T/h", alm_qhp, w=55)
        tag_spd  = _tag(755, 265, "Vit. arbre",  f"{speed:.0f}", "RPM", alarm=alm_spd, w=55)
        tag_v1   = _tag(330, 273, "Adm. HP",     f"{v1:.0f}",    "%", w=60)
        tag_vit2 = _tag(915, 264, "Vit.",         "1500",          "RPM", w=55)
        tag_turbine_int = ""
        tag_alt_group   = ""
        tag_turb_bottom = ""
        tag_alt_bottom  = ""

    if static_ids:
        vsym_v1      = _valve_symbol_static(330, 248, v1, v1_tgt, "V1",  vc1,  "syn-v1",  20)
        vsym_v2      = _valve_symbol_static(280, 175, v2, v2_tgt, "V2",  vc2,  "syn-v2",  13, orient="left")
        vsym_v3      = _valve_symbol_static(280, 335, v3, v3_tgt, "V3",  vc3,  "syn-v3",  13, orient="left")
        vsym_vbp     = _valve_symbol_static(656, 415, v_bp, v_bp_tgt,"VBP", vc_bp,"syn-vbp", 18, orient="right")
        vsym_bp_admit = _valve_symbol_static(240, 426, bp_admit, bp_admit_tgt, "BP", vc_bp_admit, "syn-bp-admit", 12)
    else:
        vsym_v1      = _valve_symbol(330, 248, v1, v1_tgt, "V1",  vc1,  20)
        vsym_v2      = _valve_symbol(280, 175, v2, v2_tgt, "V2",  vc2,  13, orient="left")
        vsym_v3      = _valve_symbol(280, 335, v3, v3_tgt, "V3",  vc3,  13, orient="left")
        vsym_vbp     = _valve_symbol(656, 415, v_bp, v_bp_tgt,"VBP", vc_bp, 18, orient="right")
        vsym_bp_admit = _valve_symbol(240, 426, bp_admit, bp_admit_tgt, "BP", vc_bp_admit, 12)

    # Table ÉTAT SYSTÈME — conditionnelle (masquée sur page Simulation)
    _table_svg = f"""
  <!-- ════ ÉTAT SYSTÈME — TABLE PAGINÉE ════ -->
  <rect x="948" y="368" width="432" height="202" rx="8"
        fill="#060d1a" stroke="#1e3a5f" stroke-width="1.5"/>
  <rect x="949" y="369" width="430" height="21" rx="7" fill="rgba(15,23,42,0.9)"/>
  <rect x="949" y="379" width="430" height="11"         fill="rgba(15,23,42,0.9)"/>
  <text x="960" y="384" fill="#475569" font-size="11" font-weight="700"
        text-anchor="middle" onclick="window.tblPage(-1)" style="cursor:pointer">◀</text>
  <text x="1090" y="384" fill="#64748b" font-size="9" text-anchor="middle"
        letter-spacing="2" font-weight="600">ÉTAT SYSTÈME</text>
  <circle id="syn-tbl-ind1" cx="1258" cy="380" r="3" fill="#e2e8f0"/>
  <circle id="syn-tbl-ind2" cx="1272" cy="380" r="3" fill="#334155"/>
  <circle id="syn-tbl-ind3" cx="1286" cy="380" r="3" fill="#334155"/>
  <circle{sid("tbl-dot")} cx="1315" cy="380" r="5"
          fill="{c_tbl_dot}" class="{tbl_pulse}"/>
  <text x="1368" y="384" fill="#475569" font-size="11" font-weight="700"
        text-anchor="middle" onclick="window.tblPage(1)" style="cursor:pointer">▶</text>
  <line x1="948" y1="390" x2="1380" y2="390" stroke="#0f2744" stroke-width="0.8"/>
  <line x1="1034" y1="390" x2="1034" y2="570" stroke="#0f2744" stroke-width="0.8"/>
  <line x1="1121" y1="390" x2="1121" y2="570" stroke="#0f2744" stroke-width="0.8"/>
  <line x1="1207" y1="390" x2="1207" y2="570" stroke="#0f2744" stroke-width="0.8"/>
  <line x1="1294" y1="390" x2="1294" y2="570" stroke="#0f2744" stroke-width="0.8"/>
  <line x1="948" y1="474" x2="1380" y2="474" stroke="#0f2744" stroke-width="0.8"/>
  <!-- Pages réordonnées : du plus critique (sécurité mécanique) au moins critique (monitoring BP) -->
  <g id="syn-tbl-page1">
  <!-- Page 1 — Sécurité mécanique / Protection -->
  <!-- Row 1 : Vitesse, Vib. Av., Vib. Ar., Dép. Axial, Huile P. -->
  <text x="991"  y="406" fill="#64748b" font-size="9" text-anchor="middle">Vitesse</text>
  <text{sid("tbl-spd")} x="991" y="438" fill="{c_tbl_spd}" font-size="19"
       font-weight="700" text-anchor="middle">{speed:.0f}</text>
  <text x="991"  y="452" fill="#475569" font-size="8.5" text-anchor="middle">RPM</text>
  <text x="1077" y="406" fill="#64748b" font-size="9" text-anchor="middle">Vib. Av.</text>
  <text{sid("tbl-vib")} x="1077" y="438" fill="{c_tbl_vib}" font-size="19"
       font-weight="700" text-anchor="middle">{vib_fwd:.1f}</text>
  <text x="1077" y="452" fill="#475569" font-size="8.5" text-anchor="middle">mm/s</text>
  <text x="1163" y="406" fill="#64748b" font-size="9" text-anchor="middle">Vib. Ar.</text>
  <text{sid("tbl2-vibaft")} x="1163" y="438" fill="{c_tbl2_vibaft}" font-size="19"
       font-weight="700" text-anchor="middle">{vib_aft:.1f}</text>
  <text x="1163" y="452" fill="#475569" font-size="8.5" text-anchor="middle">mm/s</text>
  <text x="1250" y="406" fill="#64748b" font-size="9" text-anchor="middle">Dép. Axial</text>
  <text{sid("tbl2-axial")} x="1250" y="438" fill="{c_tbl2_axial}" font-size="16"
       font-weight="700" text-anchor="middle">{axial:+.2f}</text>
  <text x="1250" y="452" fill="#475569" font-size="8.5" text-anchor="middle">mm</text>
  <text x="1337" y="406" fill="#64748b" font-size="9" text-anchor="middle">Huile P.</text>
  <text{sid("tbl2-oilp")} x="1337" y="438" fill="{c_tbl2_oilp}" font-size="19"
       font-weight="700" text-anchor="middle">{oil_p:.2f}</text>
  <text x="1337" y="452" fill="#475569" font-size="8.5" text-anchor="middle">bar</text>
  <!-- Row 2 : T° Pal.Av., T° Pal.Ar., Huile T°, P HP, T HP -->
  <text x="991"  y="492" fill="#64748b" font-size="9" text-anchor="middle">T° Pal.Av.</text>
  <text{sid("tbl2-tfwd")} x="991" y="524" fill="{c_tbl2_tfwd}" font-size="19"
       font-weight="700" text-anchor="middle">{temp_fwd:.0f}</text>
  <text x="991"  y="540" fill="#475569" font-size="8.5" text-anchor="middle">°C</text>
  <text x="1077" y="492" fill="#64748b" font-size="9" text-anchor="middle">T° Pal.Ar.</text>
  <text{sid("tbl2-taft")} x="1077" y="524" fill="{c_tbl2_taft}" font-size="19"
       font-weight="700" text-anchor="middle">{temp_aft:.0f}</text>
  <text x="1077" y="540" fill="#475569" font-size="8.5" text-anchor="middle">°C</text>
  <text x="1163" y="492" fill="#64748b" font-size="9" text-anchor="middle">Huile T°</text>
  <text{sid("tbl-oilt")} x="1163" y="524" fill="{c_tbl_oilt}" font-size="19"
       font-weight="700" text-anchor="middle">{oil_t:.0f}</text>
  <text x="1163" y="540" fill="#475569" font-size="8.5" text-anchor="middle">°C</text>
  <text x="1250" y="492" fill="#64748b" font-size="9" text-anchor="middle">P HP</text>
  <text{sid("tbl-php")} x="1250" y="524" fill="{c_tbl_php}" font-size="19"
       font-weight="700" text-anchor="middle">{p_hp:.1f}</text>
  <text x="1250" y="540" fill="#475569" font-size="8.5" text-anchor="middle">bar</text>
  <text x="1337" y="492" fill="#64748b" font-size="9" text-anchor="middle">T HP</text>
  <text{sid("tbl-thp")} x="1337" y="524" fill="{c_tbl_thp}" font-size="19"
       font-weight="700" text-anchor="middle">{t_hp:.0f}</text>
  <text x="1337" y="540" fill="#475569" font-size="8.5" text-anchor="middle">°C</text>
  </g>
  <g id="syn-tbl-page2" display="none">
  <!-- Page 2 — Opérationnel / Électrique -->
  <!-- Row 1 : P active, Fréquence, cos φ, Courant, Dilatation -->
  <text x="991"  y="406" fill="#64748b" font-size="9" text-anchor="middle">P activ.</text>
  <text{sid("tbl3-power")} x="991" y="438" fill="{alt_col}" font-size="19"
       font-weight="700" text-anchor="middle">{power:.1f}</text>
  <text x="991"  y="452" fill="#475569" font-size="8.5" text-anchor="middle">MW</text>
  <text x="1077" y="406" fill="#64748b" font-size="9" text-anchor="middle">Fréquence</text>
  <text{sid("tbl2-freq")} x="1077" y="438" fill="{c_tbl2_freq}" font-size="19"
       font-weight="700" text-anchor="middle">{freq:.2f}</text>
  <text x="1077" y="452" fill="#475569" font-size="8.5" text-anchor="middle">Hz</text>
  <text x="1163" y="406" fill="#64748b" font-size="9" text-anchor="middle">cos φ</text>
  <text{sid("tbl3-pf")} x="1163" y="438" fill="{'#ef4444' if alm_pf else '#fbbf24'}" font-size="19"
       font-weight="700" text-anchor="middle">{pf:.3f}</text>
  <text x="1250" y="406" fill="#64748b" font-size="9" text-anchor="middle">Courant</text>
  <text{sid("tbl3-ia")} x="1250" y="438" fill="{'#ef4444' if alm_ia else '#10b981'}" font-size="19"
       font-weight="700" text-anchor="middle">{i_a:.0f}</text>
  <text x="1250" y="452" fill="#475569" font-size="8.5" text-anchor="middle">A</text>
  <text x="1337" y="406" fill="#64748b" font-size="9" text-anchor="middle">Dilatation</text>
  <text{sid("tbl2-casing")} x="1337" y="438" fill="{c_tbl2_casing}" font-size="19"
       font-weight="700" text-anchor="middle">{casing:.1f}</text>
  <text x="1337" y="452" fill="#475569" font-size="8.5" text-anchor="middle">mm</text>
  <!-- Row 2 : V1 HP, Valve BP, Q HP, Rendement, P barillet -->
  <text x="991"  y="492" fill="#64748b" font-size="9" text-anchor="middle">V1 HP</text>
  <text{sid("tbl-v1")} x="991" y="524" fill="{c_tbl_v1}" font-size="19"
       font-weight="700" text-anchor="middle">{v1:.0f}</text>
  <text x="991"  y="540" fill="#475569" font-size="8.5" text-anchor="middle">%</text>
  <text x="1077" y="492" fill="#64748b" font-size="9" text-anchor="middle">Valve BP</text>
  <text{sid("tbl-vbp")} x="1077" y="524" fill="{c_tbl_vbp}" font-size="19"
       font-weight="700" text-anchor="middle">{v_bp:.0f}</text>
  <text x="1077" y="540" fill="#475569" font-size="8.5" text-anchor="middle">%</text>
  <text x="1163" y="492" fill="#64748b" font-size="9" text-anchor="middle">Q HP</text>
  <text{sid("tbl-qhp")} x="1163" y="524" fill="#f97316" font-size="19"
       font-weight="700" text-anchor="middle">{q_hp:.0f}</text>
  <text x="1163" y="540" fill="#475569" font-size="8.5" text-anchor="middle">T/h</text>
  <text x="1250" y="492" fill="#64748b" font-size="9" text-anchor="middle">Rendement</text>
  <text{sid("tbl-eff")} x="1250" y="524" fill="{c_tbl_eff}" font-size="19"
       font-weight="700" text-anchor="middle">{eff:.1f}</text>
  <text x="1250" y="540" fill="#475569" font-size="8.5" text-anchor="middle">%</text>
  <text x="1337" y="492" fill="#64748b" font-size="9" text-anchor="middle">P barillet</text>
  <text{sid("tbl-pbar")} x="1337" y="524" fill="{c_tbl_pbar}" font-size="19"
       font-weight="700" text-anchor="middle">{p_bar_bp:.2f}</text>
  <text x="1337" y="540" fill="#475569" font-size="8.5" text-anchor="middle">bar</text>
  </g>
  <g id="syn-tbl-page3" display="none">
  <!-- Page 3 — BP / Monitoring -->
  <!-- Row 1 (5 cellules) : P BP in, Q cond., P vide, Q réact., S appar. -->
  <text x="991"  y="406" fill="#64748b" font-size="9" text-anchor="middle">P BP in</text>
  <text{sid("tbl2-pbpin")} x="991" y="438" fill="{c_tbl2_pbpin}" font-size="19"
       font-weight="700" text-anchor="middle">{p_bp_in:.2f}</text>
  <text x="991"  y="452" fill="#475569" font-size="8.5" text-anchor="middle">bar</text>
  <text x="1077" y="406" fill="#64748b" font-size="9" text-anchor="middle">Q cond.</text>
  <text{sid("tbl2-qcond")} x="1077" y="438" fill="{c_tbl2_qcond}" font-size="19"
       font-weight="700" text-anchor="middle">{q_cond:.0f}</text>
  <text x="1077" y="452" fill="#475569" font-size="8.5" text-anchor="middle">T/h</text>
  <text x="1163" y="406" fill="#64748b" font-size="9" text-anchor="middle">P vide</text>
  <text{sid("tbl2-pcond")} x="1163" y="438" fill="{c_tbl2_pcond}" font-size="16"
       font-weight="700" text-anchor="middle">{p_cond:.4f}</text>
  <text x="1163" y="452" fill="#475569" font-size="8.5" text-anchor="middle">bar</text>
  <text x="1250" y="406" fill="#64748b" font-size="9" text-anchor="middle">Q réact.</text>
  <text{sid("tbl3-qmvar")} x="1250" y="438" fill="#818cf8" font-size="19"
       font-weight="700" text-anchor="middle">{q_mvar:.1f}</text>
  <text x="1250" y="452" fill="#475569" font-size="8.5" text-anchor="middle">MVAR</text>
  <text x="1337" y="406" fill="#64748b" font-size="9" text-anchor="middle">S appar.</text>
  <text{sid("tbl3-smva")} x="1337" y="438" fill="#fbbf24" font-size="19"
       font-weight="700" text-anchor="middle">{s_mva:.1f}</text>
  <text x="1337" y="452" fill="#475569" font-size="8.5" text-anchor="middle">MVA</text>
  </g>""" if show_table else ""

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -52 1430 664"
     width="100%" height="100%"
     preserveAspectRatio="xMidYMin meet"
     style="font-family:'Share Tech Mono',monospace;background:transparent">
  <defs>
    <filter id="go" x="-25%" y="-25%" width="150%" height="150%">
      <feGaussianBlur stdDeviation="5" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="gb" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="7" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="gg" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="gr" x="-25%" y="-25%" width="150%" height="150%">
      <feGaussianBlur stdDeviation="8" result="b"/>
      <feFlood flood-color="#ef4444" flood-opacity="0.4" result="g"/>
      <feComposite in="g" in2="b" operator="in" result="sg"/>
      <feMerge><feMergeNode in="sg"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="gp" x="-25%" y="-25%" width="150%" height="150%">
      <feGaussianBlur stdDeviation="6" result="b"/>
      <feFlood flood-color="#a855f7" flood-opacity="0.35" result="g"/>
      <feComposite in="g" in2="b" operator="in" result="sg"/>
      <feMerge><feMergeNode in="sg"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <marker id="arr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
      <path d="M0,0 L0,6 L6,3 Z" fill="#94a3b8"/>
    </marker>
    <style>
      .spin  {{ transform-box:fill-box; transform-origin:center;
                animation:spin {spin_dur} linear infinite; }}
      @keyframes spin {{ to {{ transform:rotate(360deg); }} }}

      .vibrate {{ animation:vibrate 0.08s linear infinite; }}
      @keyframes vibrate {{
        25%  {{ transform:translate(1px,1px);  }}
        75%  {{ transform:translate(-1px,-1px); }}
      }}

      .flow-hp {{ stroke-dasharray:14,7;
                  animation:flow {flow_dur} linear infinite; }}
      .flow-bp {{ stroke-dasharray:10,6;
                  animation:flow {flow_dur} linear infinite; }}
      .flow-el {{ stroke-dasharray:12,6;
                  animation:flow 0.8s linear infinite; }}
      @keyframes flow {{ to {{ stroke-dashoffset:-21; }} }}

      .pulse {{ animation:pulse 2s ease-in-out infinite; }}
      @keyframes pulse {{
        0%,100% {{ opacity:1; }}
        50%     {{ opacity:0.5; }}
      }}
      .blink {{ animation:blink 1s step-end infinite; }}
      @keyframes blink {{ 50% {{ opacity:0; }} }}

      /* NOUVEAU : halo au survol des tags cliquables */
      .hover-tag:hover rect {{
        stroke-width: 1.8 !important;
        filter: brightness(1.3);
      }}
      .hover-tag:hover {{
        filter: drop-shadow(0 0 6px rgba(96,165,250,0.5));
      }}
    </style>
  </defs>

  <!-- Tooltip hint (visible seulement sur / — Dashboard) -->
  <text x="-18" y="-24" fill="#1e3a5f" font-size="8.5" font-family="Share Tech Mono">
    ▲ Cliquez sur un tag pour voir sa tendance
  </text>

  <!-- Scénario actif -->
  {f'''<rect x="300" y="6" width="{70 + len(scenario)*7}" height="28" rx="4"
        fill="rgba(239,68,68,0.1)" stroke="#ef4444" stroke-width="1"/>
  <circle cx="315" cy="20" r="5" fill="#ef4444" class="blink"/>
  <text x="326" y="24" fill="#ef4444" font-size="10" font-weight="700">{scenario.upper()}</text>''' if scenario else ''}

  <!-- Légende flux -->
  <line x1="1180" y1="-30" x2="1155" y2="-30" stroke="#f97316" stroke-width="4"/>
  <text x="1185" y="-27" fill="#94a3b8" font-size="9">Vapeur HP</text>
  <line x1="1265" y1="-30" x2="1240" y2="-30" stroke="#a78bfa" stroke-width="4"/>
  <text x="1270" y="-27" fill="#94a3b8" font-size="9">Extr. BP</text>
  <line x1="1340" y1="-30" x2="1315" y2="-30" stroke="#38bdf8" stroke-width="4"/>
  <text x="1345" y="-27" fill="#94a3b8" font-size="9">Vapeur Sortie</text>
  <line x1="1180" y1="-15" x2="1155" y2="-15" stroke="#10b981" stroke-width="4"/>
  <text x="1185" y="-12" fill="#94a3b8" font-size="9">Électrique</text>
  <line x1="1265" y1="-15" x2="1240" y2="-15" stroke="#1d4ed8" stroke-width="2" stroke-dasharray="4,2"/>
  <text x="1270" y="-12" fill="#94a3b8" font-size="9">Mvm Mécanique</text>

  <!-- ════ SOURCE VAPEUR HP ════ -->
  <g filter="url(#go)">
    <rect x="18" y="188" width="125" height="160" rx="10"
          fill="#0a101a" stroke="{hp_col}" stroke-width="1.8"/>
  </g>
  <text x="80" y="211" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">SOURCE HP</text>
  <text x="80" y="226" fill="#64748b" font-size="8.5" text-anchor="middle">Unité Acide Sulfurique</text>
  <text{sid("hp-flame")} x="80" y="245" fill="{hp_col}" font-size="22" text-anchor="middle"
        class="{'pulse' if alm_thp else ''}">{'⚠' if alm_thp else '🔥'}</text>

  {tag_php}
  {tag_thp}

  <!-- ════ LIGNE HP ════ -->
  <line x1="143" y1="248" x2="195" y2="248"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"/>
  {_instrument_circle(175, 248, "FT", "#f97316")}
  {tag_qhp}
  <line x1="186" y1="248" x2="220" y2="248"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"
        class="flow-hp"/>

  <!-- ════ ESV ════ -->
  <g>
    <rect x="220" y="236" width="30" height="24" rx="4"
          fill="#0a101a" stroke="#94a3b8" stroke-width="1"/>
    <text x="235" y="250" fill="#94a3b8" font-size="8" font-weight="700"
          text-anchor="middle">ESV</text>
    <text id="syn-esv-state" x="235" y="259" fill="#10b981" font-size="7.5" text-anchor="middle">OPEN</text>
  </g>
  <line x1="250" y1="248" x2="272" y2="248"
        stroke="#f97316" stroke-width="9" class="flow-hp"/>
  <circle cx="280" cy="248" r="7" fill="#f97316" opacity="0.85"/>
  <line x1="280" y1="248" x2="310" y2="248"
        stroke="#f97316" stroke-width="9" class="flow-hp"/>

  {vsym_v1}
  {tag_v1}
  <line x1="350" y1="248" x2="385" y2="248"
        stroke="#f97316" stroke-width="9" class="flow-hp"/>

  <line x1="280" y1="248" x2="280" y2="180"
        stroke="#f97316" stroke-width="6" class="flow-hp"/>
  {vsym_v2}
  <line x1="280" y1="162" x2="390" y2="162"
        stroke="#f97316" stroke-width="6" class="flow-hp"/>
  <text x="340" y="155" fill="#f97316" font-size="8" text-anchor="middle" font-weight="700">Vanne Eq. Haut (~7%)</text>

  <line x1="280" y1="248" x2="280" y2="330"
        stroke="#f97316" stroke-width="6" class="flow-hp"/>
  {vsym_v3}
  <line x1="280" y1="348" x2="390" y2="348"
        stroke="#f97316" stroke-width="6" class="flow-hp"/>
  <text x="340" y="358" fill="#f97316" font-size="8" text-anchor="middle" font-weight="700">Vanne Eq. Bas (~7%)</text>

  <!-- ════ BLOC DÉPLACEMENT & DILATATION ════ -->
  <rect x="385" y="74" width="140" height="52" rx="4"
        fill="rgba(15,23,42,0.75)" stroke="#64748b" stroke-width="0.8"/>
  <text x="455" y="87" fill="#94a3b8" font-size="8.5" text-anchor="middle" font-weight="700">DILATATION THERMIQUE</text>
  <text x="418" y="100" fill="#64748b" font-size="8" text-anchor="middle">Déplac. Axial</text>
  <text{sid("axial-val")} x="418" y="115" fill="#38bdf8" font-size="11" font-weight="700" text-anchor="middle">+{axial:.2f}</text>
  <text x="438" y="115" fill="#64748b" font-size="8">mm</text>
  <text x="490" y="100" fill="#64748b" font-size="8" text-anchor="middle">Corps</text>
  <text{sid("casing-val")} x="490" y="115" fill="#38bdf8" font-size="11" font-weight="700" text-anchor="middle">{casing:.1f}</text>
  <text x="510" y="115" fill="#64748b" font-size="8">mm</text>

  <!-- ════ BLOC TURBINE HP/BP ════ -->
  <g class="{turb_cls}">
    <rect x="385" y="130" width="340" height="260" rx="12"
          fill="#060d1a" stroke="#3b82f6" stroke-width="2" filter="url(#gb)"/>
    <text x="555" y="167" fill="#60a5fa" font-size="13" font-weight="700"
          text-anchor="middle" letter-spacing="2">TURBINE À VAPEUR</text>
    <text x="555" y="181" fill="#475569" font-size="9" text-anchor="middle">
      Détente 2 étages — HP → Extraction → BP
    </text>

    <rect x="400" y="185" width="130" height="115" rx="6"
          fill="transparent" stroke="#3b82f6" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="465" y="202" fill="#93c5fd" font-size="11" font-weight="600" text-anchor="middle">HP</text>
    <line x1="410" y1="213" x2="522" y2="280" stroke="#3b82f6" stroke-width="1.2"/>
    <line x1="522" y1="213" x2="410" y2="280" stroke="#3b82f6" stroke-width="1.2"/>
    <g transform="translate(465,248)"><g class="spin">
      <circle r="16" fill="#060d1a" stroke="#3b82f6" stroke-width="1.5"/>
      <circle r="3" fill="#3b82f6"/>
      <line x1="-16" y1="0" x2="16" y2="0" stroke="#3b82f6" stroke-width="1.5"/>
      <line x1="0" y1="-16" x2="0" y2="16" stroke="#3b82f6" stroke-width="1.5"/>
      <line x1="-11" y1="-11" x2="11" y2="11" stroke="#3b82f6" stroke-width="1"/>
      <line x1="11" y1="-11" x2="-11" y2="11" stroke="#3b82f6" stroke-width="1"/>
    </g></g>

    <circle cx="549" cy="248" r="6" fill="#a78bfa" stroke="#0a101a" stroke-width="1.5"/>
    <text x="549" y="260" fill="#a78bfa" font-size="7.5" font-weight="600" text-anchor="middle">Ext.</text>
    <text x="549" y="269" fill="#a78bfa" font-size="7" text-anchor="middle">(4.5 bar)</text>

    <rect x="570" y="185" width="140" height="115" rx="6"
          fill="transparent" stroke="#38bdf8" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="640" y="202" fill="#7dd3fc" font-size="11" font-weight="600" text-anchor="middle">BP</text>
    <line x1="580" y1="213" x2="700" y2="280" stroke="#38bdf8" stroke-width="1.2"/>
    <line x1="700" y1="213" x2="580" y2="280" stroke="#38bdf8" stroke-width="1.2"/>
    <g transform="translate(640,248)"><g class="spin">
      <circle r="16" fill="#060d1a" stroke="#38bdf8" stroke-width="1.5"/>
      <circle r="3" fill="#38bdf8"/>
      <line x1="-16" y1="0" x2="16" y2="0" stroke="#38bdf8" stroke-width="1.5"/>
      <line x1="0" y1="-16" x2="0" y2="16" stroke="#38bdf8" stroke-width="1.5"/>
      <line x1="-11" y1="-11" x2="11" y2="11" stroke="#38bdf8" stroke-width="1"/>
      <line x1="11" y1="-11" x2="-11" y2="11" stroke="#38bdf8" stroke-width="1"/>
    </g></g>
    <circle cx="656" cy="300" r="5" fill="#38bdf8"/>
    <text x="664" y="310" fill="#38bdf8" font-size="8">Ext. BP</text>
    <rect x="735" y="175" width="44" height="66" rx="4" fill="rgba(15,23,42,0.85)" stroke="#64748b" stroke-width="0.8"/>
    <text x="757" y="187" fill="#cbd5e1" font-size="9" font-weight="700" text-anchor="middle">P. AV</text>
    <text{sid("vibfwd-val")} x="757" y="202" fill="{'#ef4444' if vib_fwd > 4.5 else '#fbbf24'}" font-size="11" font-weight="700" text-anchor="middle">{vib_fwd:.1f}</text>
    <text x="757" y="213" fill="#64748b" font-size="8" text-anchor="middle">mm/s</text>
    <text{sid("tempfwd-val")} x="757" y="228" fill="#38bdf8" font-size="10" text-anchor="middle">{temp_fwd:.0f}</text>
    <text x="757" y="239" fill="#64748b" font-size="8" text-anchor="middle">°C</text>

    <rect x="895" y="175" width="44" height="66" rx="4" fill="rgba(15,23,42,0.85)" stroke="#64748b" stroke-width="0.8"/>
    <text x="917" y="187" fill="#cbd5e1" font-size="9" font-weight="700" text-anchor="middle">P. AR</text>
    <text{sid("vibaft-val")} x="917" y="202" fill="{'#ef4444' if vib_aft > 4.5 else '#fbbf24'}" font-size="11" font-weight="700" text-anchor="middle">{vib_aft:.1f}</text>
    <text x="917" y="213" fill="#64748b" font-size="8" text-anchor="middle">mm/s</text>
    <text{sid("tempaft-val")} x="917" y="228" fill="#38bdf8" font-size="10" text-anchor="middle">{temp_aft:.0f}</text>
    <text x="917" y="239" fill="#64748b" font-size="8" text-anchor="middle">°C</text>
    <line x1="395" y1="248" x2="720" y2="248"
          stroke="#1d4ed8" stroke-width="4" stroke-dasharray="8,5" class="flow-hp" opacity="0.5"/>   
  </g>

  {tag_turbine_int}
  {tag_turb_bottom}

  <!-- ════ EXTRACTION → BARILLET BP ════ -->
  <line x1="549" y1="130" x2="549" y2="55"
      stroke="#a78bfa" stroke-width="7" stroke-linecap="round" class="flow-bp"/>
  {_instrument_circle(549, 95, "PT", "#a78bfa")}
  <text x="562" y="98" fill="#a78bfa" font-size="8" font-weight="700">38%</text>

  <!-- ════ BARILLET BP ════ -->
  <rect id="syn-barillet-bp-rect" x="407" y="-10" width="285" height="65" rx="10"
        fill="#0a101a" stroke="#38bdf8" stroke-width="1.8" filter="url(#gb)"/>
  <text x="549" y="10" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1.5">BARILLET BP</text>
  <text x="549" y="21" fill="#64748b" font-size="7.5" text-anchor="middle">Collecteur 3 bar — Procédés AS</text>
  <line x1="417" y1="27" x2="675" y2="27" stroke="#1e3a5f" stroke-width="0.8"/>
  <text x="427" y="40" fill="#64748b" font-size="7">P</text>
  <text{sid("pbar-bp-val")} x="427" y="50" fill="#38bdf8" font-size="12" font-weight="700">{p_bar_bp:.2f}</text>
  <text x="455" y="50" fill="#64748b" font-size="7">bar</text>
  <text x="485" y="40" fill="#64748b" font-size="7">Ent.</text>
  <text id="syn-q-barillet" x="485" y="50" fill="#a78bfa" font-size="12" font-weight="700">{flow_barillet_val_in:.0f}</text>
  <text x="513" y="50" fill="#64748b" font-size="7">T/h</text>
  <line x1="547" y1="30" x2="547" y2="52" stroke="#1e3a5f" stroke-width="0.8"/>
  <text x="555" y="37" fill="#a78bfa" font-size="7">→ Chauffage AS</text>
  <text id="syn-q-chauffage" x="675" y="37" fill="#a78bfa" font-size="8" font-weight="700"
        text-anchor="end">{flow_chauffage_val:.1f} T/h</text>
  <text x="555" y="50" fill="#a78bfa" font-size="7">→ Surchauffeur AS</text>
  <text id="syn-q-surchauffeur" x="675" y="50" fill="#a78bfa" font-size="8" font-weight="700"
        text-anchor="end">{flow_surchauffeur_val:.1f} T/h</text>
  <rect id="syn-barillet-bp-blink" x="672" y="-3" width="14" height="14" rx="7"
        fill="#ef4444" class="blink"
        {'display="block"' if p_bar_bp > 5.0 else 'display="none"'}/>

  <!-- ════ TUYAU BP : TURBINE → VBP → CONDENSEUR ════ -->
  <line x1="655" y1="390" x2="655" y2="410"
        stroke="#38bdf8" stroke-width="8" stroke-linecap="round" class="flow-bp"/>
  {vsym_vbp}
  <line x1="645" y1="415" x2="465" y2="415"
        stroke="#38bdf8" stroke-width="8" class="flow-bp"/>
  <line x1="460" y1="415" x2="460" y2="445"
        stroke="#38bdf8" stroke-width="8" class="flow-bp"/>

  <!-- ════ CONDENSEUR ════ -->
  <rect x="290" y="435" width="195" height="125" rx="10"
        fill="#060d1a" stroke="#38bdf8" stroke-width="1.8" filter="url(#gb)"/>
  <text x="387" y="452" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">CONDENSEUR</text>
  <text x="387" y="464" fill="#64748b" font-size="8" text-anchor="middle">Pression quasi nulle (absolue)</text>
  <text x="387" y="475" fill="#10b981" font-size="8" font-weight="600"
        text-anchor="middle">① VP HP → Condenseur</text>
  <rect x="292" y="480" width="192" height="74" rx="4"
        fill="rgba(15,23,42,0.75)" stroke="#0f2744" stroke-width="0.8"/>
  <text x="318" y="495" fill="#64748b" font-size="8">P vide</text>
  <text{sid("pcond-val")} x="318" y="510" fill="#38bdf8" font-size="11" font-weight="700">{p_cond:.4f}</text>
  <text x="318" y="522" fill="#64748b" font-size="7.5">bar</text>
  <line x1="363" y1="482" x2="363" y2="552" stroke="#0f2744" stroke-width="0.8"/>
  <text x="376" y="495" fill="#64748b" font-size="8">T BP sortie</text>
  <text{sid("tbp-val")} x="376" y="510" fill="#38bdf8" font-size="11" font-weight="700">{t_bp:.0f}</text>
  <text x="376" y="522" fill="#64748b" font-size="7.5">°C</text>
  <line x1="424" y1="482" x2="424" y2="552" stroke="#0f2744" stroke-width="0.8"/>
  <text x="438" y="495" fill="#64748b" font-size="8">Q eau</text>
  <text{sid("qcond2-val")} x="438" y="510" fill="#38bdf8" font-size="11" font-weight="700">{q_cond:.0f}</text>
  <text x="438" y="522" fill="#64748b" font-size="7.5">T/h</text>
  <text x="387" y="550" fill="#1e3a5f" font-size="7"
        text-anchor="middle">Δh = ṁ × (h_in − h_out) → Eau chaude recyclée</text>

  <!-- ════ ARBRE TURBINE → RÉDUCTEUR ════ -->
  <line x1="725" y1="248" x2="785" y2="248"
        stroke="#1d4ed8" stroke-width="6" stroke-dasharray="8,5" class="flow-hp"/>
  {_instrument_circle(755, 248, "ST", "#1d4ed8")}

  <!-- ════ RÉDUCTEUR ════ -->
  <rect x="785" y="190" width="100" height="120" rx="10"
        fill="#0a101a" stroke="#10b981" stroke-width="1.8" filter="url(#gg)"/>
  <text x="835" y="212" fill="#f8fafc" font-size="10" font-weight="600"
        text-anchor="middle" letter-spacing="1">RÉDUCTEUR</text>
  <g transform="translate(835,248)">
    <g class="spin">
      <circle r="20" fill="none" stroke="#10b981" stroke-width="1.5"/>
      <circle r="4" fill="#10b981"/>
      <line x1="-20" y1="0" x2="-14" y2="0" stroke="#10b981" stroke-width="2"/>
      <line x1="14" y1="0" x2="20" y2="0" stroke="#10b981" stroke-width="2"/>
      <line x1="0" y1="-20" x2="0" y2="-14" stroke="#10b981" stroke-width="2"/>
      <line x1="0" y1="14" x2="0" y2="20" stroke="#10b981" stroke-width="2"/>
    </g>
  </g>
  <text x="835" y="283" fill="#34d399" font-size="9" text-anchor="middle">÷ 4.29</text>
  <text id="syn-alt-rpm-lbl" x="835" y="296" fill="#10b981" font-size="10" font-weight="700"
        text-anchor="middle">→ 1500 RPM</text>
  <text{sid("freq-val")} x="835" y="308" fill="#34d399" font-size="9" font-weight="700" text-anchor="middle">{freq:.2f} <tspan fill="#064e3b" font-size="8">Hz · 2 pôles</tspan></text>

  <line x1="885" y1="248" x2="945" y2="248"
        stroke="#1d4ed8" stroke-width="6" stroke-dasharray="8,5" class="flow-hp"/>
  {_instrument_circle(915, 248, "ST", "#1d4ed8")}
  {tag_vit2}

  <!-- ════ EXCITATRICE / AVR ════ -->
  <rect id="syn-avr-rect" x="945" y="33" width="165" height="70" rx="10"
        fill="#0a101a" stroke="#a855f7" stroke-width="1.8" filter="url(#gp)"/>
  <text x="1027" y="51" fill="#f8fafc" font-size="10.5" font-weight="700"
        text-anchor="middle" letter-spacing="1.2">EXCITATRICE / AVR</text>
  <text x="1027" y="62" fill="#475569" font-size="7.5"
        text-anchor="middle">IEEE Type 1 — K_a·1/(1+T_a·s)</text>
  <text x="958" y="78" fill="#64748b" font-size="7">E_fd</text>
  <text id="syn-avr-efd-val" x="958" y="92" fill="#a855f7"
        font-size="12" font-weight="700">1.00</text>
  <text x="983" y="92" fill="#64748b" font-size="6.5">p.u.</text>
  <rect id="syn-avr-mode-rect" x="1001" y="71" width="62" height="22" rx="4"
        fill="rgba(168,85,247,0.15)" stroke="#a855f7" stroke-width="0.8"/>
  <text id="syn-avr-mode-val" x="1032" y="86" fill="#a855f7"
        font-size="8.5" font-weight="700" text-anchor="middle">VOLTAGE</text>
  <circle id="syn-avr-sat-led" cx="1089" cy="81" r="5"
          fill="#1e293b" stroke="#a855f7" stroke-width="1"/>
  <text x="1089" y="97" fill="#64748b" font-size="6.5" text-anchor="middle">SAT</text>
  <line x1="1027" y1="103" x2="1027" y2="155"
        stroke="#a855f7" stroke-width="2" stroke-dasharray="3,2" opacity="0.8"/>
  <text x="1037" y="132" fill="#a855f7" font-size="6.5" font-weight="700">E_fd ↓</text>

  <!-- ════ ALTERNATEUR ════ -->
  <rect id="syn-alt-rect" x="945" y="155" width="165" height="200" rx="12"
        fill="#060d1a" stroke="{alt_col}" stroke-width="2"
        filter="url(#{'gr' if alm_pow else 'gg'})"/>
  <text x="1027" y="192" fill="#f8fafc" font-size="11" font-weight="700"
        text-anchor="middle" letter-spacing="1">ALTERNATEUR</text>
  <text x="1027" y="205" fill="#475569" font-size="8"
        text-anchor="middle">IEC 60034 · Topologie Étoile</text>
  
  <g transform="translate(1027,248)">
    <g class="spin">
      <circle r="36" fill="none" stroke="#10b981" stroke-width="1.5"/>
      <circle r="15" fill="#10b981"/>
      <line x1="-36" y1="0" x2="-30" y2="0" stroke="#10b981" stroke-width="2"/>
      <line x1="30" y1="0" x2="36" y2="0" stroke="#10b981" stroke-width="2"/>
      <line x1="0" y1="-36" x2="0" y2="-30" stroke="#10b981" stroke-width="2"/>
      <line x1="0" y1="30" x2="0" y2="36" stroke="#10b981" stroke-width="2"/>
    </g>
  </g>
  <text{sid("alt-tilde")} x="1027" y="260" fill="{alt_col}" font-size="30" text-anchor="middle"
        class="{'pulse' if alm_pow else ''}">~</text>

  {tag_alt_group}
  {tag_alt_bottom}

  <!-- ════ BUS BARRES ÉLECTRIQUE ════ -->
  <line x1="1110" y1="248" x2="1175" y2="248"
        stroke="#10b981" stroke-width="10" class="flow-el"/>

  <rect x="1175" y="180" width="20" height="160" rx="3"
        fill="#0a101a" stroke="#10b981" stroke-width="2"/>
  <text x="1185" y="175" fill="#10b981" font-size="8" text-anchor="middle">BB</text>
  <line x1="1178" y1="210" x2="1192" y2="210" stroke="#ef4444" stroke-width="3"/>
  <text x="1197" y="213" fill="#ef4444" font-size="7.5">L1</text>
  <line x1="1178" y1="248" x2="1192" y2="248" stroke="#f59e0b" stroke-width="3"/>
  <text x="1197" y="251" fill="#f59e0b" font-size="7.5">L2</text>
  <line x1="1178" y1="286" x2="1192" y2="286" stroke="#3b82f6" stroke-width="3"/>
  <text x="1197" y="289" fill="#3b82f6" font-size="7.5">L3</text>
  <line x1="1195" y1="248" x2="1235" y2="248"
        stroke="#10b981" stroke-width="8" class="flow-el"/>

  <!-- ════ RÉSEAU MT ════ -->
  <rect x="1235" y="165" width="140" height="175" rx="10"
        fill="#060d1a" stroke="#10b981" stroke-width="1.8" filter="url(#gg)"/>
  <text x="1305" y="190" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">RÉSEAU MT</text>
  <text x="1305" y="204" fill="#475569" font-size="8.5"
        text-anchor="middle">10.5 kV · 50 Hz · 3φ</text>
  <line x1="1265" y1="215" x2="1265" y2="260" stroke="#10b981" stroke-width="2"/>
  <line x1="1295" y1="215" x2="1295" y2="260" stroke="#10b981" stroke-width="2"/>
  <line x1="1325" y1="215" x2="1325" y2="260" stroke="#10b981" stroke-width="2"/>
  <line x1="1250" y1="225" x2="1340" y2="225" stroke="#10b981" stroke-width="1.5"/>
  <line x1="1255" y1="238" x2="1335" y2="238" stroke="#10b981" stroke-width="1.5"/>
  <rect x="1244" y="272" width="122" height="58" rx="4"
        fill="rgba(15,23,42,0.8)" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1255" y="286" fill="#64748b" font-size="8">Charge site</text>
  <text x="1255" y="298" fill="#10b981" font-size="12" font-weight="700">14.0</text>
  <text x="1255" y="309" fill="#64748b" font-size="7.5">MW</text>
  <line x1="1305" y1="274" x2="1305" y2="328" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1313" y="286" fill="#64748b" font-size="8">Excédent</text>
  <text{sid("excess-val")} x="1313" y="298" fill="#fbbf24" font-size="12" font-weight="700">{max(0, power-14):.1f}</text>
  <text x="1313" y="309" fill="#64748b" font-size="7.5">MW</text>
  <text x="1305" y="332" fill="#334155" font-size="8" text-anchor="middle">28 kV (1 min) · 40 kA (1 min)</text>

  {_table_svg}

  <!-- ════ SOURCE VAPEUR BP ════ -->
  <rect x="18" y="430" width="125" height="85" rx="8"
        fill="#0a101a" stroke="#38bdf8" stroke-width="1.2" opacity="0.7"/>
  <text x="80" y="452" fill="#94a3b8" font-size="10" font-weight="600"
        text-anchor="middle">SOURCE BP</text>
  <text x="80" y="465" fill="#475569" font-size="8"
        text-anchor="middle">Démarrage 5–10 min</text>
  <text{sid("bp-src-p")} x="80" y="488" fill="#38bdf8" font-size="11" font-weight="700"
        text-anchor="middle">{p_bp_in:.1f} <tspan fill="#64748b" font-size="8" font-weight="400">bar</tspan></text>
  <text x="80" y="503" fill="#38bdf8" font-size="11" font-weight="700"
        text-anchor="middle">226 <tspan fill="#64748b" font-size="8" font-weight="400">°C</tspan></text>
  <line x1="143" y1="472" x2="229" y2="431"
        stroke="#38bdf8" stroke-width="2" stroke-dasharray="4,4" opacity="0.4"/>
  {vsym_bp_admit}
  <line x1="251" y1="421" x2="385" y2="358"
        stroke="#38bdf8" stroke-width="2" stroke-dasharray="4,4" opacity="0.4"/>
  <text x="175" y="405" fill="#38bdf8" font-size="8" opacity="0.6">
    (démarrage uniquement)
  </text>
  <text id="syn-bp-flow-in" x="175" y="418" fill="#38bdf8" font-size="9"
        font-weight="700" text-anchor="middle">0 T/h</text>

  <!-- ════ CENTRALE HUILE LUBRIFICATION ════ -->
  <style>.flow-oil{{stroke-dasharray:8,4;animation:flow 2s linear infinite;}}</style>
  
  <!-- Ligne vers Palier Avant (P. AV) -->
  <polyline points="720,560 720,480 755,480 755,237" 
          fill="none" stroke="#fbbf24" stroke-width="1.5" opacity="0.55"
          class="flow-oil"/>

  <!-- Ligne vers Palier Arrière (P. AR) -->
  <polyline points="760,560 760,480 915,480 915,237" 
          fill="none" stroke="#fbbf24" stroke-width="1.5" opacity="0.55"
          class="flow-oil"/>

  <!-- Cadre principal -->
  <rect{sid("lube-rect")} x="550" y="445" width="380" height="155" rx="10"
       fill="rgba(15,23,42,0.85)" stroke="#10b981" stroke-width="1.8"
       filter="url(#gg)"/>
  <!-- Alarme blink (cachée par défaut) -->
  <circle{sid("lube-blink")} cx="917" cy="453" r="5" fill="#ef4444"
          display="none" class="blink"/>

  <!-- Titre -->
  <text x="740" y="462" fill="#94a3b8" font-size="9" font-weight="700"
        text-anchor="middle" letter-spacing="1">CENTRALE HUILE LUBRIFICATION</text>
  <line x1="555" y1="467" x2="925" y2="467" stroke="#1e3a5f" stroke-width="0.8"/>

  <!-- Pompe (indicateur haut-droit) -->
  <circle{sid("lube-pump-dot")} cx="882" cy="480" r="5" fill="#10b981"/>
  <text x="858" y="477" fill="#64748b" font-size="8" text-anchor="end">Pompe</text>
  <text{sid("lube-pump-val")} x="890" y="484" fill="#10b981" font-size="9"
       font-weight="700">{oil_pump}</text>

  <!-- Séparateur vertical -->
  <line x1="735" y1="467" x2="735" y2="597" stroke="#1e3a5f" stroke-width="0.8"/>
  <!-- Séparateur horizontal -->
  <line x1="555" y1="530" x2="925" y2="530" stroke="#1e3a5f" stroke-width="0.8"/>

  <!-- ── Ligne 1 : P. Huile | T° Entrée | T° Sortie ── -->
  <!-- Pression -->
  <text x="645" y="490" fill="#64748b" font-size="8" text-anchor="middle">P. Huile</text>
  <text{sid("lube-press-val")} x="645" y="509" fill="{'#ef4444' if oil_p < 1.2 or oil_p > 2.5 else '#fbbf24'}"
       font-size="17" font-weight="700" text-anchor="middle"
       {'class="blink"' if oil_p < 1.2 else ''}>{oil_p:.2f}</text>
  <text x="645" y="520" fill="#64748b" font-size="8" text-anchor="middle">bar</text>

  <!-- T° Entrée paliers -->
  <text x="830" y="490" fill="#64748b" font-size="8" text-anchor="middle">T° Entrée</text>
  <text{sid("lube-tin-val")} x="830" y="509" fill="{'#ef4444' if oil_t > 55 else '#fbbf24'}"
       font-size="17" font-weight="700" text-anchor="middle">{oil_t:.1f}</text>
  <text x="830" y="520" fill="#64748b" font-size="8" text-anchor="middle">°C</text>

  <!-- T° Sortie paliers -->
  <text x="740" y="490" fill="#64748b" font-size="8" text-anchor="middle">T° Sortie</text>
  <text{sid("lube-tout-val")} x="740" y="509" fill="{'#ef4444' if oil_t_out > 70 else '#f97316'}"
       font-size="17" font-weight="700" text-anchor="middle">{oil_t_out:.1f}</text>
  <text x="740" y="520" fill="#64748b" font-size="8" text-anchor="middle">°C</text>

  <!-- ── Ligne 2 : Niveau | ΔP Filtre | indicateur paliers ── -->
  <!-- Niveau réservoir -->
  <!-- Barre de progression niveau -->
  <rect x="560" y="550" width="140" height="10" rx="3" fill="#0f2744" stroke="#1e3a5f" stroke-width="0.5"/>
  <rect x="560" y="550" width="{max(0, min(140, 140 * oil_lvl / 100)):.0f}" height="10" rx="3"
        fill="{'#ef4444' if oil_lvl < 60 else '#10b981'}" opacity="0.85"/>
  <text x="630" y="545" fill="#64748b" font-size="8" text-anchor="middle">Niveau réservoir</text>
  <text{sid("lube-level-val")} x="630" y="575" fill="{'#ef4444' if oil_lvl < 60 else '#10b981'}"
       font-size="14" font-weight="700" text-anchor="middle">{oil_lvl:.0f} %</text>

  <!-- ΔP Filtre -->
  <text x="830" y="545" fill="#64748b" font-size="8" text-anchor="middle">ΔP Filtre</text>
  <text{sid("lube-dpfilter-val")} x="830" y="564" fill="{'#ef4444' if oil_dp > 0.8 else '#a78bfa'}"
       font-size="17" font-weight="700" text-anchor="middle"
       {'class="pulse"' if oil_dp > 0.8 else ''}>{oil_dp:.2f}</text>
  <text x="830" y="577" fill="#64748b" font-size="8" text-anchor="middle">bar</text>

  <!-- Icône pompe (silhouette) -->
  <circle cx="740" cy="560" r="14" fill="rgba(16,185,129,0.08)" stroke="#10b981" stroke-width="1.2"/>
  
<!-- Losange centré dans le cercle - Version corrigée -->
<path d="M730,560 L740,552 L750,560 L740,568 Z" 
      fill="#10b981" opacity="0.7"/>

<!-- Traits / détails de la pompe -->
<path d="M740,546 L740,552 M740,568 L740,574 M726,560 L732,560 M748,560 L754,560"
      stroke="#10b981" 
      stroke-width="1.2" 
      opacity="0.5"/>

  <!-- ════ OVERLAY AU/TRIP (masqué par défaut, activé via JS) ════ -->
  <g id="syn-trip-overlay" display="none" class="blink">
    <rect x="0" y="0" width="1400" height="635" fill="rgba(127,29,29,0.55)" rx="0"/>
    <rect x="350" y="270" width="700" height="95" rx="10"
          fill="rgba(127,29,29,0.92)" stroke="#ef4444" stroke-width="2.5"/>
    <text x="700" y="305" fill="#fca5a5" font-size="22" font-weight="700"
          text-anchor="middle" font-family="Share Tech Mono" letter-spacing="3">
      ⛔  ARRÊT D'URGENCE ACTIF
    </text>
    <text x="700" y="338" fill="#f87171" font-size="13" font-weight="600"
          text-anchor="middle" font-family="Share Tech Mono" letter-spacing="1.5">
      Machine TRIPPÉE — ESV fermée — V1 = 0%
    </text>
  </g>

</svg>"""

    div_kwargs = {"id": "gta-synoptic-inner"} if static_ids else {}

    return html.Div(
        [dash_dangerously_set_inner_html.DangerouslySetInnerHTML(svg)],
        style={
            "width":        "100%",
            "height":       "635px",
            "background":   "#060d1a",
            "overflowX":    "hidden",
            "overflowY":    "hidden",
            "borderRadius": "10px",
            "border":       "1px solid #0f2744",
            "padding":      "6px",
        },
        **div_kwargs
    )


# ── Helpers internes (version dynamique, page Simulation) ────────────────────

def _tag(x, y, label, value, unit, alarm=False, anchor="middle", w=90):
    val_color = "#ef4444" if alarm else "#e2e8f0"
    bkg       = "rgba(239,68,68,0.12)" if alarm else "rgba(15,23,42,0.75)"
    border    = "#ef4444" if alarm else "#1e3a5f"
    xi = x - w//2 if anchor == "middle" else x
    xt = x if anchor == "middle" else x + w//2
    return f"""
    <g class="{'blink' if alarm else ''}">
      <rect x="{xi}" y="{y}" width="{w}" height="34"
            rx="4" fill="{bkg}" stroke="{border}" stroke-width="0.8"/>
      <text x="{xt}" y="{y+11}"
            fill="#64748b" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{label}</text>
      <text x="{xt}" y="{y+25}"
            fill="{val_color}" font-size="12" font-weight="700" text-anchor="middle"
            font-family="Share Tech Mono">{value} <tspan fill="#64748b" font-size="9" font-weight="400">{unit}</tspan></text>
    </g>"""


def _valve_symbol(cx, cy, pct, target, name, col, size=18, orient="top"):
    if orient == "right":
        actuator = f"""
        <line x1="{cx+size}" y1="{cy}" x2="{cx+size+10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx+size+10} {cy-size+2} Q {cx+size+18} {cy} {cx+size+10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text x="{cx+size+22}" y="{cy-8}" fill="#94a3b8" font-size="9" text-anchor="start" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    elif orient == "left":
        actuator = f"""
        <line x1="{cx-size}" y1="{cy}" x2="{cx-size-10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size-10} {cy-size+2} Q {cx-size-18} {cy} {cx-size-10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text x="{cx-size-22}" y="{cy-8}" fill="#94a3b8" font-size="9" text-anchor="end" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    else:
        actuator = f"""
        <line x1="{cx}" y1="{cy-size}" x2="{cx}" y2="{cy-size-5}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size+2} {cy-size-5} Q {cx} {cy-size-12} {cx+size-2} {cy-size-5} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text x="{cx}" y="{cy-size-12}" fill="#94a3b8" font-size="9" text-anchor="middle" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'

    return f"""
    {tgt_txt}
    {actuator}
    <circle cx="{cx}" cy="{cy}" r="{size}" fill="#0a101a" stroke="{col}" stroke-width="2"/>
    <text x="{cx}" y="{cy-1}" fill="{col}" font-size="9" font-weight="700" text-anchor="middle" font-family="Share Tech Mono">{name}</text>
    <text x="{cx}" y="{cy+9}" fill="{col}" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{pct:.0f}%</text>"""