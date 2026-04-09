"""
components/gta_synoptic.py  [FIX-5a]
Schéma synoptique SCADA du GTA — niveau industriel.

REFACTORING PERFORMANCE :
  - create_gta_synoptic(data) → create_gta_synoptic_static()
    La structure SVG est générée UNE SEULE FOIS avec des valeurs par défaut.
    Chaque élément dynamique porte un id="syn-*" stable.
  - La mise à jour des valeurs numériques et des couleurs est déléguée
    à la fonction JS patchGtaSynoptic(data) dans assets/synoptic_patch.js.
  - create_gta_synoptic(data) est conservée pour la page Simulation
    (update_sim_ui) qui l'appelle avec les données simulées — ce callback
    est moins fréquent (triggered par store-simulation-data, 1s, guard page).

Nouveautés vs version initiale :
  - 5 vannes : V1 (HP), V2/V3 (équilibrage), valve_mp (extraction MP), valve_bp (condenseur)
  - Tous les nouveaux paramètres : I(A), Q(MVAR), S(MVA), pressure_bp_barillet,
    steam_flow_condenser, pressure_condenser, reactive_power, apparent_power
  - Bus barres électrique triphasé
  - Tags SCADA sur chaque mesure (étiquette + valeur + unité)
  - Indicateurs d'alarme sur chaque point de mesure
"""

from dash import html
import dash_dangerously_set_inner_html


STATUS_COLORS = {
    "NORMAL":   {"stroke": "#10b981", "glow": "rgba(16,185,129,0.25)", "label": "#10b981"},
    "DEGRADED": {"stroke": "#f59e0b", "glow": "rgba(245,158,11,0.25)",  "label": "#f59e0b"},
    "CRITICAL": {"stroke": "#ef4444", "glow": "rgba(239,68,68,0.3)",    "label": "#ef4444"},
}

# ── Valeurs par défaut (état nominal) ────────────────────────────────────────
_DEFAULTS = {
    "status":               "NORMAL",
    "pressure_hp":          60.0,
    "temperature_hp":       486.0,
    "steam_flow_hp":        120.0,
    "pressure_bp_in":       4.5,
    "temperature_bp":       226.0,
    "pressure_mp_barillet": 9.5,
    "pressure_bp_barillet": 3.0,
    "steam_flow_condenser": 74.0,
    "pressure_condenser":   0.0064,
    "turbine_speed":        6435.0,
    "efficiency":           92.0,
    "active_power":         24.0,
    "power_factor":         0.85,
    "reactive_power":       21.4,
    "apparent_power":       41.0,
    "voltage":              10.5,
    "current_a":            2254.0,
    "valve_v1":             100.0,
    "valve_v2":             100.0,
    "valve_v3":             100.0,
    "valve_mp":             50.0,
    "valve_bp":             80.0,
}


def _vc(pct, hi_col="#f97316", lo_col="#ef4444"):
    """Couleur d'une vanne selon % ouverture."""
    if pct >= 75: return hi_col
    if pct >= 30: return "#f59e0b"
    return lo_col


def _alarm(val, lo, hi):
    """Retourne True si la valeur est hors plage normale."""
    return val < lo or val > hi


def _tag_static(x, y, label, elem_id, default_value, default_unit,
                alarm=False, anchor="middle", w=90):
    """
    Génère un tag SCADA avec un id stable sur la zone valeur.
    Le fond/bordure peut changer via JS (setAttribute data-alarm).
    """
    val_color = "#ef4444" if alarm else "#e2e8f0"
    bkg       = "rgba(239,68,68,0.12)" if alarm else "rgba(15,23,42,0.75)"
    border    = "#ef4444" if alarm else "#1e3a5f"
    xi = x - w//2 if anchor == "middle" else x
    xt = x if anchor == "middle" else x + w//2
    return f"""
    <g id="{elem_id}-g">
      <rect id="{elem_id}-rect" x="{xi}" y="{y}" width="{w}" height="34"
            rx="4" fill="{bkg}" stroke="{border}" stroke-width="0.8"/>
      <text x="{xt}" y="{y+11}"
            fill="#64748b" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{label}</text>
      <text id="{elem_id}-val" x="{xt}" y="{y+25}"
            fill="{val_color}" font-size="12" font-weight="700" text-anchor="middle"
            font-family="Share Tech Mono">{default_value} <tspan id="{elem_id}-unit" fill="#64748b" font-size="9" font-weight="400">{default_unit}</tspan></text>
    </g>"""


def _valve_symbol_static(cx, cy, pct, target, name, col, vid, size=18, orient="top"):
    """Symbole vanne SCADA : corps circulaire avec servomoteur, orientable."""
    if orient == "right":
        actuator = f"""
        <line x1="{cx+size}" y1="{cy}" x2="{cx+size+10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx+size+10} {cy-size+2} Q {cx+size+18} {cy} {cx+size+10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text id="{vid}-tgt" x="{cx+size+22}" y="{cy-8}" fill="#94a3b8" font-size="7.5" text-anchor="start" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    elif orient == "left":
        actuator = f"""
        <line x1="{cx-size}" y1="{cy}" x2="{cx-size-10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size-10} {cy-size+2} Q {cx-size-18} {cy} {cx-size-10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text id="{vid}-tgt" x="{cx-size-22}" y="{cy-8}" fill="#94a3b8" font-size="7.5" text-anchor="end" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    else:
        actuator = f"""
        <line x1="{cx}" y1="{cy-size}" x2="{cx}" y2="{cy-size-5}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size+2} {cy-size-5} Q {cx} {cy-size-12} {cx+size-2} {cy-size-5} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text id="{vid}-tgt" x="{cx}" y="{cy-size-12}" fill="#94a3b8" font-size="7.5" text-anchor="middle" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'

    return f"""
    {tgt_txt}
    {actuator}
    <circle id="{vid}-circle" cx="{cx}" cy="{cy}" r="{size}" fill="#0a101a" stroke="{col}" stroke-width="2"/>
    <text x="{cx}" y="{cy-1}" fill="{col}" font-size="9" font-weight="700" text-anchor="middle" font-family="Share Tech Mono">{name}</text>
    <text id="{vid}-pct" x="{cx}" y="{cy+9}" fill="{col}" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{pct:.0f}%</text>"""


def _instrument_circle(cx, cy, label, col="#60a5fa", r=11):
    """Cercle d'instrument de mesure (style P&ID)."""
    return f"""
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="#0a101a" stroke="{col}" stroke-width="1.2"/>
    <text x="{cx}" y="{cy+4}" fill="{col}" font-size="8" font-weight="600"
          text-anchor="middle" font-family="Share Tech Mono">{label}</text>"""


# ─────────────────────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────────────────────

def create_gta_synoptic_static() -> html.Div:
    """
    [FIX-5a] Retourne la structure SVG statique avec valeurs par défaut.
    Appelée UNE SEULE FOIS au chargement de la page Dashboard (au layout).
    Les mises à jour sont ensuite gérées par patchGtaSynoptic() en JS.
    """
    return _build_synoptic_div(_DEFAULTS, static_ids=True)


def create_gta_synoptic(data: dict) -> html.Div:
    """
    Version dynamique (Python complet) utilisée par la page Simulation.
    La page Simulation a son propre store (store-simulation-data) et son
    propre callback (update_sim_ui) — moins fréquent et protégé par guard.
    """
    merged = {**_DEFAULTS, **{k: v for k, v in data.items() if v is not None}}
    return _build_synoptic_div(merged, static_ids=False)


def _build_synoptic_div(data: dict, static_ids: bool) -> html.Div:
    """Construit le SVG complet. static_ids=True → IDs syn-* pour patch JS."""

    status  = data.get("status", "NORMAL")
    p_hp    = data.get("pressure_hp",      60.0)
    t_hp    = data.get("temperature_hp",  486.0)
    q_hp    = data.get("steam_flow_hp",   120.0)

    p_bp_in  = data.get("pressure_bp_in",       4.5)
    t_bp     = data.get("temperature_bp",      226.0)
    p_bar_mp = data.get("pressure_mp_barillet", 9.5)   # barillet MP soutirage HP
    p_bar_bp = data.get("pressure_bp_barillet", 3.0)   # barillet BP distribution    q_cond   = data.get("steam_flow_condenser",  74.0)
    q_cond   = data.get("steam_flow_condenser",  74.0)
    p_cond   = data.get("pressure_condenser",  0.0064)

    speed   = data.get("turbine_speed",   6435.0)
    eff     = data.get("efficiency",        92.0)

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
    v_mp    = data.get("valve_mp",   50.0)
    v_mp_tgt= data.get("valve_mp_target", v_mp)
    v_bp    = data.get("valve_bp",   80.0)
    v_bp_tgt= data.get("valve_bp_target", v_bp)

    # ── Meca / Aux
    freq    = data.get("grid_frequency", 50.00)
    vib_fwd = data.get("vib_bearing_fwd", 2.1)
    vib_aft = data.get("vib_bearing_aft", 1.8)
    temp_fwd= data.get("temp_bearing_fwd", 74.0)
    temp_aft= data.get("temp_bearing_aft", 76.0)
    oil_p   = data.get("lube_oil_press", 1.5)
    oil_t   = data.get("lube_oil_temp", 45.0)
    axial   = data.get("axial_displacement", 0.2)
    casing  = data.get("casing_expansion", 5.0)

    scenario = data.get("scenario")

    # ── Distribution flux BP (calculé depuis données disponibles) ──
    _q_hp_eff          = q_hp * (v1 / 100.0)
    _q_extract_mp      = _q_hp_eff * 0.20 * (v_mp / 100.0)
    flow_barillet_val    = round(_q_extract_mp * 0.50, 1)
    flow_chauffage_val   = round(_q_extract_mp * 0.30, 1)
    flow_surchauffeur_val = round(_q_extract_mp * 0.20, 1)

    # ── Alarmes ──────────────────────────────────────────────────────────────
    alm_php  = _alarm(p_hp,  55, 65)
    alm_thp  = _alarm(t_hp, 420, 500)
    alm_qhp  = _alarm(q_hp, 100, 130)
    alm_spd  = _alarm(speed, 6300, 6550)
    alm_pow  = power > 30.0
    alm_pf   = _alarm(pf, 0.82, 0.86)
    alm_eff  = eff < 85.0
    alm_pbar_mp = _alarm(p_bar_mp, 8.0, 11.0)
    alm_pbar_bp = p_bar_bp > 3.5
    alm_ia   = i_a > 3000

    # ── Couleurs dynamiques ───────────────────────────────────────────────────
    sc       = STATUS_COLORS.get(status, STATUS_COLORS["NORMAL"])["stroke"]
    hp_col   = "#ef4444" if alm_thp else "#f97316"
    alt_col  = "#ef4444" if alm_pow else ("#f59e0b" if power > 24 else "#10b981")
    bar_col  = "#ef4444" if alm_pbar_mp else "#a78bfa"
    vc1      = _vc(v1,  "#f97316")
    vc2      = _vc(v2,  "#60a5fa")
    vc3      = _vc(v3,  "#60a5fa")
    vc_mp    = _vc(v_mp,"#a78bfa")
    vc_bp    = _vc(v_bp,"#3b82f6")

    # ── Animations ───────────────────────────────────────────────────────────
    flow_dur = f"{max(0.3, 120.0/max(1, q_hp)):.2f}s" if q_hp > 5 else "99999s"
    rpm_norm = min(max((speed - 5500)/1500, 0), 1)
    spin_dur = f"{max(0.4, 2.0 - rpm_norm*1.6):.2f}s"
    turb_cls = "vibrate" if speed > 6500 else ""

    t_warn_design = t_hp < 460

    # ── IDs pour les éléments patchables (uniquement en mode static) ──────────
    def sid(name):
        """Retourne l'id SVG si static_ids, sinon chaîne vide (pas d'id)."""
        return f' id="syn-{name}"' if static_ids else ""

    # ── Construction des tags SCADA ───────────────────────────────────────────
    if static_ids:
        tag_php  = _tag_static(80,  251, "Pression",    "syn-php",  f"{p_hp:.1f}",  "bar",  alm_php)
        tag_thp  = _tag_static(80,  289, "Température", "syn-thp",  f"{t_hp:.0f}",  "°C",   alm_thp)
        tag_qhp  = _tag_static(185, 193, "Débit HP",    "syn-qhp",  f"{q_hp:.0f}",  "T/h",  alm_qhp, w=55)
        tag_spd  = _tag_static(755, 265, "Vit. arbre",  "syn-spd",  f"{speed:.0f}", "RPM",  alm_spd, w=55)
        tag_v1   = _tag_static(330, 273, "Adm. HP",     "syn-v1t",  f"{v1:.0f}",    "%", w=60)
        tag_pout = _tag_static(1142,262, "P active",    "syn-pout", f"{power:.1f}","MW",  alm_pow, w=65)
        tag_vit2 = _tag_static(915, 264, "Vit.",        "syn-vit2", "1500",          "RPM", w=55)
    else:
        tag_php  = _tag(80,  251, "Pression",    f"{p_hp:.1f}",  "bar", alm_php)
        tag_thp  = _tag(80,  289, "Température", f"{t_hp:.0f}",  "°C",  alm_thp)
        tag_qhp  = _tag(185, 193, "Débit HP",    f"{q_hp:.0f}",  "T/h", alm_qhp, w=55)
        tag_spd  = _tag(755, 265, "Vit. arbre",  f"{speed:.0f}", "RPM", alarm=alm_spd, w=55)
        tag_v1   = _tag(330, 273, "Adm. HP",     f"{v1:.0f}",    "%", w=60)
        tag_pout = _tag(1142,262, "P active",     f"{power:.1f}","MW", alarm=alm_pow, w=65)
        tag_vit2 = _tag(915, 264, "Vit.",         "1500",          "RPM", w=55)

    # ── Symboles vannes ───────────────────────────────────────────────────────
    if static_ids:
        vsym_v1  = _valve_symbol_static(330, 248, v1, v1_tgt, "V1",  vc1,  "syn-v1",  20)
        vsym_v2  = _valve_symbol_static(280, 175, v2, v2_tgt, "V2",  vc2,  "syn-v2",  13, orient="left")
        vsym_v3  = _valve_symbol_static(280, 335, v3, v3_tgt, "V3",  vc3,  "syn-v3",  13, orient="left")
        vsym_vmp = _valve_symbol_static(544, 62, v_mp, v_mp_tgt,"VMP", vc_mp, "syn-vmp", 17, orient="right")
        vsym_vbp = _valve_symbol_static(656, 415, v_bp, v_bp_tgt,"VBP", vc_bp,"syn-vbp", 18, orient="top")
    else:
        # Appel direct — _valve_symbol est défini dans ce même module
        vsym_v1  = _valve_symbol(330, 248, v1, v1_tgt, "V1",  vc1,  20)
        vsym_v2  = _valve_symbol(280, 175, v2, v2_tgt, "V2",  vc2,  13, orient="left")
        vsym_v3  = _valve_symbol(280, 335, v3, v3_tgt, "V3",  vc3,  13, orient="left")
        vsym_vmp = _valve_symbol(544, 62, v_mp, v_mp_tgt,"VMP", vc_mp, 17, orient="right")
        vsym_vbp = _valve_symbol(656, 415, v_bp, v_bp_tgt,"VBP", vc_bp, 18, orient="top")

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -38 1430 643"
     width="100%" height="100%"
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
    </style>
  </defs>
  <!-- Scénario actif -->
  {f'''<rect x="300" y="6" width="{70 + len(scenario)*7}" height="28" rx="4"
        fill="rgba(239,68,68,0.1)" stroke="#ef4444" stroke-width="1"/>
  <circle cx="315" cy="20" r="5" fill="#ef4444" class="blink"/>
  <text x="326" y="24" fill="#ef4444" font-size="10" font-weight="700">{scenario.upper()}</text>''' if scenario else ''}

  <!-- Légende flux -->
  <line x1="1180" y1="-20" x2="1155" y2="-20" stroke="#f97316" stroke-width="4"/>
  <text x="1185" y="-17" fill="#94a3b8" font-size="9">Vapeur HP</text>
  <line x1="1265" y1="-20" x2="1240" y2="-20" stroke="#3b82f6" stroke-width="4"/>
  <text x="1270" y="-17" fill="#94a3b8" font-size="9">Vapeur BP</text>
  <line x1="1350" y1="-20" x2="1325" y2="-20" stroke="#a78bfa" stroke-width="4"/>
  <text x="1355" y="-17" fill="#94a3b8" font-size="9">Extr. MP</text>
  <line x1="1180" y1="-5" x2="1155" y2="-5" stroke="#10b981" stroke-width="4"/>
  <text x="1185" y="-2" fill="#94a3b8" font-size="9">Électrique</text>
  <line x1="1265" y1="-5" x2="1240" y2="-5" stroke="#60a5fa" stroke-width="2" stroke-dasharray="4,2"/>
  <text x="1270" y="-2" fill="#94a3b8" font-size="9">Équilibrage</text>

  <!-- ════ SOURCE VAPEUR HP ════ -->
  <g filter="url(#go)">
    <rect x="18" y="188" width="125" height="160" rx="10"
          fill="#0a101a" stroke="{hp_col}" stroke-width="1.8"/>
  </g>
  <text x="80" y="211" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">SOURCE HP</text>
  <text x="80" y="226" fill="#64748b" font-size="8.5" text-anchor="middle">Unité Acide Sulfurique</text>

  <!-- Flamme animée -->
  <text{sid("hp-flame")} x="80" y="245" fill="{hp_col}" font-size="22" text-anchor="middle"
        class="{'pulse' if alm_thp else ''}">{'⚠' if alm_thp else '🔥'}</text>

  <!-- Tags source HP -->
  {tag_php}
  {tag_thp}

  <!-- ════ LIGNE HP ════ -->
  <line x1="143" y1="248" x2="195" y2="248"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"/>
  {_instrument_circle(195, 248, "FT", "#f97316")}
  {tag_qhp}
  <line x1="206" y1="248" x2="240" y2="248"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"
        class="flow-hp"/>

  <!-- ════ ESV ════ -->
  <g>
    <rect x="240" y="236" width="30" height="24" rx="4"
          fill="#0a101a" stroke="#94a3b8" stroke-width="1"/>
    <text x="255" y="250" fill="#94a3b8" font-size="8" font-weight="700"
          text-anchor="middle">ESV</text>
    <text x="255" y="259" fill="#10b981" font-size="7.5" text-anchor="middle">OPEN</text>
  </g>
  <line x1="270" y1="248" x2="300" y2="248"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"
        class="flow-hp"/>

  <!-- ════ VANNE V1 ADMISSION HP ════ -->
  {vsym_v1}
  {tag_v1}
  <line x1="350" y1="248" x2="385" y2="248"
        stroke="#f97316" stroke-width="10" class="flow-hp"/>

  <!-- V2 équilibrage haut -->
  <line x1="280" y1="248" x2="280" y2="180"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  {vsym_v2}
  <line x1="280" y1="162" x2="390" y2="162"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  <text x="330" y="155" fill="#60a5fa" font-size="8" text-anchor="middle">Équilibrage ~7%</text>

  <!-- V3 équilibrage bas -->
  <line x1="280" y1="248" x2="280" y2="330"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  {vsym_v3}
  <line x1="280" y1="348" x2="390" y2="348"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  <text x="330" y="358" fill="#60a5fa" font-size="8" text-anchor="middle">Équilibrage ~7%</text>
  
  <!-- ════ BLOC DÉPLACEMENT & DILATATION (Au-dessus Turbine) ════ -->
  <rect x="385" y="76" width="135" height="42" rx="4"
        fill="rgba(15,23,42,0.75)" stroke="#64748b" stroke-width="0.8"/>
  <text x="452" y="88" fill="#94a3b8" font-size="8.5" text-anchor="middle" font-weight="700">DILATATION THERMIQUE</text>
  <text x="420" y="100" fill="#64748b" font-size="7" text-anchor="middle">Déplac. Axial</text>
  <text{sid("axial-val")} x="420" y="112" fill="#38bdf8" font-size="11" font-weight="700" text-anchor="middle">+{axial:.2f}</text>
  <text x="440" y="112" fill="#64748b" font-size="7">mm</text>
  <text x="485" y="100" fill="#64748b" font-size="7" text-anchor="middle">Corps</text>
  <text{sid("casing-val")} x="485" y="112" fill="#38bdf8" font-size="11" font-weight="700" text-anchor="middle">{casing:.1f}</text>
  <text x="505" y="112" fill="#64748b" font-size="7">mm</text>

  <!-- ════ BLOC TURBINE HP/MP/BP ════ -->
  <g class="{turb_cls}">
    <rect x="385" y="130" width="340" height="260" rx="12"
          fill="#060d1a" stroke="#3b82f6" stroke-width="2" filter="url(#gb)"/>
    <text x="555" y="160" fill="#60a5fa" font-size="13" font-weight="700"
          text-anchor="middle" letter-spacing="2">TURBINE À VAPEUR</text>
    <text x="555" y="175" fill="#475569" font-size="9" text-anchor="middle">
      Réduction multi-étagée — HP → MP → BP
    </text>

    <!-- Étage HP -->
    <rect x="400" y="185" width="85" height="115" rx="6"
          fill="transparent" stroke="#3b82f6" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="442" y="202" fill="#93c5fd" font-size="11" font-weight="600" text-anchor="middle">HP</text>
    <line x1="408" y1="213" x2="478" y2="280" stroke="#3b82f6" stroke-width="1.2"/>
    <line x1="478" y1="213" x2="408" y2="280" stroke="#3b82f6" stroke-width="1.2"/>
    <g transform="translate(442,248)"><g class="spin">
      <circle r="13" fill="#060d1a" stroke="#3b82f6" stroke-width="1.5"/>
      <circle r="3" fill="#3b82f6"/>
      <line x1="-13" y1="0" x2="13" y2="0" stroke="#3b82f6" stroke-width="1.5"/>
      <line x1="0" y1="-13" x2="0" y2="13" stroke="#3b82f6" stroke-width="1.5"/>
      <line x1="-9" y1="-9" x2="9" y2="9" stroke="#3b82f6" stroke-width="1"/>
      <line x1="9" y1="-9" x2="-9" y2="9" stroke="#3b82f6" stroke-width="1"/>
    </g></g>
    <text{sid("hp-stages")} x="442" y="297" fill="#60a5fa" font-size="7.5" text-anchor="middle">{p_hp:.0f}→{p_bp_in:.1f} bar</text>

    <!-- Étage MP -->
    <rect x="502" y="185" width="85" height="115" rx="6"
          fill="transparent" stroke="#818cf8" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="544" y="202" fill="#a5b4fc" font-size="11" font-weight="600" text-anchor="middle">MP</text>
    <line x1="510" y1="213" x2="580" y2="280" stroke="#818cf8" stroke-width="1.2"/>
    <line x1="580" y1="213" x2="510" y2="280" stroke="#818cf8" stroke-width="1.2"/>
    <g transform="translate(544,248)"><g class="spin">
      <circle r="13" fill="#060d1a" stroke="#818cf8" stroke-width="1.5"/>
      <circle r="3" fill="#818cf8"/>
      <line x1="-13" y1="0" x2="13" y2="0" stroke="#818cf8" stroke-width="1.5"/>
      <line x1="0" y1="-13" x2="0" y2="13" stroke="#818cf8" stroke-width="1.5"/>
      <line x1="-9" y1="-9" x2="9" y2="9" stroke="#818cf8" stroke-width="1"/>
      <line x1="9" y1="-9" x2="-9" y2="9" stroke="#818cf8" stroke-width="1"/>
    </g></g>
    <circle cx="544" cy="185" r="5" fill="#a78bfa"/>
    <text x="552" y="182" fill="#a78bfa" font-size="8">Ext. MP</text>

    <!-- Étage BP -->
    <rect x="604" y="185" width="105" height="115" rx="6"
          fill="transparent" stroke="#38bdf8" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="656" y="202" fill="#7dd3fc" font-size="11" font-weight="600" text-anchor="middle">BP</text>
    <line x1="612" y1="213" x2="700" y2="280" stroke="#38bdf8" stroke-width="1.2"/>
    <line x1="700" y1="213" x2="612" y2="280" stroke="#38bdf8" stroke-width="1.2"/>
    <g transform="translate(656,248)"><g class="spin">
      <circle r="15" fill="#060d1a" stroke="#38bdf8" stroke-width="1.5"/>
      <circle r="3" fill="#38bdf8"/>
      <line x1="-15" y1="0" x2="15" y2="0" stroke="#38bdf8" stroke-width="1.5"/>
      <line x1="0" y1="-15" x2="0" y2="15" stroke="#38bdf8" stroke-width="1.5"/>
      <line x1="-11" y1="-11" x2="11" y2="11" stroke="#38bdf8" stroke-width="1"/>
      <line x1="11" y1="-11" x2="-11" y2="11" stroke="#38bdf8" stroke-width="1"/>
    </g></g>
    <text{sid("bp-label")} x="656" y="295" fill="#38bdf8" font-size="7.5" text-anchor="middle">{p_bp_in:.1f} bar · {t_bp:.0f}°C</text>
    <circle cx="656" cy="300" r="5" fill="#38bdf8"/>
    <text x="664" y="310" fill="#38bdf8" font-size="8">Ext. BP</text>

    <!-- PALIERS AVANT / ARRIÈRE (Supervision Mécanique) -->
    <!-- Palier Avant -->
    <rect x="735" y="178" width="40" height="58" rx="4" fill="rgba(15,23,42,0.85)" stroke="#64748b" stroke-width="0.8"/>
    <text x="755" y="188" fill="#cbd5e1" font-size="7" font-weight="700" text-anchor="middle">P. AV</text>
    <text{sid("vibfwd-val")} x="755" y="202" fill="{'#ef4444' if vib_fwd > 4.5 else '#fbbf24'}" font-size="10" font-weight="700" text-anchor="middle">{vib_fwd:.1f}</text>
    <text x="755" y="210" fill="#64748b" font-size="6" text-anchor="middle">mm/s</text>
    <text{sid("tempfwd-val")} x="755" y="222" fill="#38bdf8" font-size="9" text-anchor="middle">{temp_fwd:.0f}</text>
    <text x="755" y="230" fill="#64748b" font-size="6" text-anchor="middle">°C</text>

    <!-- Palier Arrière -->
    <rect x="895" y="178" width="40" height="58" rx="4" fill="rgba(15,23,42,0.85)" stroke="#64748b" stroke-width="0.8"/>
    <text x="915" y="188" fill="#cbd5e1" font-size="7" font-weight="700" text-anchor="middle">P. AR</text>
    <text{sid("vibaft-val")} x="915" y="202" fill="{'#ef4444' if vib_aft > 4.5 else '#fbbf24'}" font-size="10" font-weight="700" text-anchor="middle">{vib_aft:.1f}</text>
    <text x="915" y="210" fill="#64748b" font-size="6" text-anchor="middle">mm/s</text>
    <text{sid("tempaft-val")} x="915" y="222" fill="#38bdf8" font-size="9" text-anchor="middle">{temp_aft:.0f}</text>
    <text x="915" y="230" fill="#64748b" font-size="6" text-anchor="middle">°C</text>

    <!-- Arbre commun -->
    <line x1="395" y1="248" x2="720" y2="248"
          stroke="#1d4ed8" stroke-width="4" stroke-dasharray="8,5" class="flow-hp" opacity="0.5"/>

    <!-- Footer turbine [FIX: centrage 4 colonnes] -->
<rect x="395" y="315" width="330" height="62" rx="6"
      fill="rgba(10,16,26,0.85)" stroke="#1e3a5f" stroke-width="0.8"/>

<!-- Col 1 — VITESSE  (cx=436) -->
<text x="436" y="325" fill="#64748b" font-size="7.5" text-anchor="middle">VITESSE</text>
<text{sid("speed-val")} x="436" y="340" fill="{'#ef4444' if alm_spd else '#60a5fa'}"
      font-size="14" font-weight="700" text-anchor="middle">{speed:.0f}</text>
<text x="436" y="352" fill="#64748b" font-size="7" text-anchor="middle">RPM</text>
<line x1="478" y1="319" x2="478" y2="373" stroke="#1e3a5f" stroke-width="0.8"/>

<!-- Col 2 — RENDEMENT  (cx=519) -->
<text x="519" y="325" fill="#64748b" font-size="7.5" text-anchor="middle">RENDEMENT</text>
<text{sid("eff-val")} x="519" y="340" fill="{'#ef4444' if alm_eff else '#10b981'}"
      font-size="14" font-weight="700" text-anchor="middle">{eff:.1f}</text>
<text x="519" y="352" fill="#64748b" font-size="7" text-anchor="middle">%</text>
<line x1="560" y1="319" x2="560" y2="373" stroke="#1e3a5f" stroke-width="0.8"/>

<!-- Col 3 — PRESS. BP  (cx=601) -->
<text x="601" y="325" fill="#64748b" font-size="7.5" text-anchor="middle">PRESS. BP</text>
<text{sid("pbp-val")} x="601" y="340" fill="#38bdf8"
      font-size="14" font-weight="700" text-anchor="middle">{p_bp_in:.2f}</text>
<text x="601" y="352" fill="#64748b" font-size="7" text-anchor="middle">bar</text>
<line x1="643" y1="319" x2="643" y2="373" stroke="#1e3a5f" stroke-width="0.8"/>

<!-- Col 4 — Q COND.  (cx=684) -->
<text x="684" y="325" fill="#64748b" font-size="7.5" text-anchor="middle">Q COND.</text>
<text{sid("qcond-val")} x="684" y="340" fill="#38bdf8"
      font-size="14" font-weight="700" text-anchor="middle">{q_cond:.0f}</text>
<text x="684" y="352" fill="#64748b" font-size="7" text-anchor="middle">T/h</text>

<!-- Formule centrée -->
<text x="560" y="372" fill="#1e3a5f" font-size="7"
      text-anchor="middle">Détente adiabatique — Δh = ṁ × (h_in − h_out)</text>
  </g>

  <!-- ════ EXTRACTION MP → VANNE_MP → BARILLET [SHIFT -20px] ════ -->
  <line x1="544" y1="130" x2="544" y2="0"
      stroke="#a78bfa" stroke-width="6" stroke-linecap="round" class="flow-bp"/>
  {_instrument_circle(544, 105, "PT", "#a78bfa")}
  {vsym_vmp}

<!-- ════ BARILLET MP (~9.5 bar) ════ -->
<rect id="syn-barillet-mp-rect" x="480" y="-20" width="130" height="50" rx="8"
      fill="#0a101a" stroke="{bar_col}" stroke-width="1.8"/>
<text x="545" y="0" fill="#f8fafc" font-size="10" font-weight="600"
      text-anchor="middle" letter-spacing="1">BARILLET MP</text>
<text{sid("pbar-mp-val")} x="545" y="15" fill="{bar_col}" font-size="11" font-weight="700"
      text-anchor="middle">{p_bar_mp:.2f} <tspan fill="#64748b" font-size="8" font-weight="400">bar</tspan></text>

<!-- [BARILLET BP déplacé — voir section DISTRIBUTION BP ci-dessous] -->


<!-- Sorties barillet [centre y = -50 + 50/2 = -25] -->
<line x1="480" y1="5" x2="455" y2="5" stroke="#a78bfa" stroke-width="3"/>
<text x="450" y="4" fill="#94a3b8" font-size="8" text-anchor="end">→ Acid. Sulf.</text>
<text x="450" y="11" fill="#94a3b8" font-size="8" text-anchor="end">→ Surchauffeur</text>
<line x1="610" y1="5" x2="635" y2="5" stroke="#a78bfa" stroke-width="3"/>
<text x="638" y="8" fill="#94a3b8" font-size="8">→ Réseau vapeur</text>

  <!-- ════ DISTRIBUTION BP ════ -->
  <!-- Tuyau BP sortie turbine → VBP (actuateur vers le haut) -->
  <line x1="656" y1="390" x2="656" y2="410"
        stroke="#38bdf8" stroke-width="8" stroke-linecap="round" class="flow-bp"/>
  {vsym_vbp}

  <!-- Ligne VBP → Nœud de distribution -->
  <line x1="656" y1="433" x2="656" y2="468"
        stroke="#38bdf8" stroke-width="8" class="flow-bp"/>
  <!-- Nœud de distribution (T-junction) -->
  <circle cx="656" cy="468" r="7" fill="#38bdf8" opacity="0.85"/>
  <!-- Bras vertical ↓ : nœud → BARILLET BP -->
  <line x1="656" y1="468" x2="656" y2="490"
        stroke="#38bdf8" stroke-width="8" class="flow-bp"/>
  <!-- Bras horizontal → : nœud → CONDENSEUR -->
  <line x1="656" y1="468" x2="762" y2="468"
        stroke="#38bdf8" stroke-width="6" class="flow-bp"/>

  <!-- ════ BARILLET BP — Position principale ════ -->
  <rect id="syn-barillet-bp-rect" x="555" y="490" width="200" height="100" rx="8"
        fill="#0a101a" stroke="#38bdf8" stroke-width="1.8" filter="url(#gb)"/>
  <text x="655" y="507" fill="#f8fafc" font-size="10" font-weight="600"
        text-anchor="middle" letter-spacing="1">BARILLET BP</text>

  <!-- Pression barillet BP -->
  <text{sid("pbar-bp-val")} x="655" y="523" fill="#38bdf8" font-size="14" font-weight="700"
        text-anchor="middle">{p_bar_bp:.2f} <tspan fill="#64748b" font-size="9" font-weight="400">bar</tspan></text>

  <!-- Alarme barillet BP -->
  <rect id="syn-barillet-bp-blink" x="736" y="484" width="16" height="16" rx="8"
        fill="#ef4444" class="blink"
        {'display="block"' if p_bar_bp > 3.5 else 'display="none"'}/>

  <!-- Séparateur + 4 destinations VP BP -->
  <line x1="560" y1="534" x2="750" y2="534" stroke="#1e3a5f" stroke-width="0.8"/>

  <!-- 1. VP HP → Condenseur (flux principal, affiché dans le condenseur) -->
  <text x="560" y="548" fill="#10b981" font-size="8" font-weight="600">① VP HP → Condenseur</text>
  <text{sid("q-barillet-hp")} x="750" y="548" fill="#10b981" font-size="8" font-weight="700"
        text-anchor="end">{q_cond:.0f} T/h</text>

  <!-- 2. VP BP 3 bar → Barillet -->
  <text x="560" y="560" fill="#38bdf8" font-size="7.5">② 3 bar → Barillet</text>
  <text id="syn-q-barillet" x="750" y="560" fill="#38bdf8" font-size="8" font-weight="700"
        text-anchor="end">{flow_barillet_val:.1f} T/h</text>

  <!-- 3. VP BP Chauffage eau AS -->
  <text x="560" y="571" fill="#a78bfa" font-size="7.5">③ Chauffage Eau AS</text>
  <text id="syn-q-chauffage" x="750" y="571" fill="#a78bfa" font-size="8" font-weight="700"
        text-anchor="end">{flow_chauffage_val:.1f} T/h</text>

  <!-- 4. VP BP Surchauffeur AS -->
  <text x="560" y="582" fill="#a78bfa" font-size="7.5">④ Surchauffeur AS</text>
  <text id="syn-q-surchauffeur" x="750" y="582" fill="#a78bfa" font-size="8" font-weight="700"
        text-anchor="end">{flow_surchauffeur_val:.1f} T/h</text>

  <!-- ════ CENTRALE HUILE LUBRIFICATION ════ -->
  <rect x="350" y="490" width="130" height="60" rx="6"
        fill="rgba(10,16,26,0.9)" stroke="#eab308" stroke-width="1.2"/>
  <text x="415" y="500" fill="#fde047" font-size="8.5" font-weight="700" text-anchor="middle" letter-spacing="1">HUILE GRAISSAGE</text>
  <text x="415" y="508" fill="#64748b" font-size="6" text-anchor="middle">Refroidie par Eau de Norya</text>
  <text x="380" y="520" fill="#64748b" font-size="7" text-anchor="middle">Pression</text>
  <text{sid("oilp-val")} x="380" y="534" fill="#eab308" font-size="12" font-weight="700" text-anchor="middle">{oil_p:.2f}</text>
  <text x="402" y="534" fill="#64748b" font-size="7">bar</text>
  <text x="450" y="520" fill="#64748b" font-size="7" text-anchor="middle">Temp.</text>
  <text{sid("oilt-val")} x="450" y="534" fill="#eab308" font-size="12" font-weight="700" text-anchor="middle">{oil_t:.1f}</text>
  <text x="470" y="534" fill="#64748b" font-size="7">°C</text>
  <line x1="415" y1="514" x2="415" y2="542" stroke="#1e3a5f" stroke-width="1"/>

  <!-- ════ CONDENSEUR — À droite du BARILLET BP ════ -->
  <rect x="762" y="455" width="195" height="125" rx="10"
        fill="#060d1a" stroke="#38bdf8" stroke-width="1.8" filter="url(#gb)"/>
  <text x="859" y="472" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">CONDENSEUR</text>
  <text x="859" y="484" fill="#64748b" font-size="8" text-anchor="middle">Pression quasi nulle (absolue)</text>
  <!-- Label flux principal -->
  <text x="859" y="495" fill="#10b981" font-size="8" font-weight="600"
        text-anchor="middle">① VP HP → Condenseur</text>
  <!-- Colonnes P vide / T sortie / Q eau -->
  <rect x="764" y="500" width="192" height="74" rx="4"
        fill="rgba(15,23,42,0.75)" stroke="#0f2744" stroke-width="0.8"/>
  <text x="790" y="515" fill="#64748b" font-size="8">P vide</text>
  <text{sid("pcond-val")} x="790" y="530" fill="#38bdf8" font-size="11" font-weight="700">{p_cond:.4f}</text>
  <text x="790" y="542" fill="#64748b" font-size="7.5">bar</text>
  <line x1="835" y1="502" x2="835" y2="572" stroke="#0f2744" stroke-width="0.8"/>
  <text x="848" y="515" fill="#64748b" font-size="8">T BP sortie</text>
  <text{sid("tbp-val")} x="848" y="530" fill="#38bdf8" font-size="11" font-weight="700">{t_bp:.0f}</text>
  <text x="848" y="542" fill="#64748b" font-size="7.5">°C</text>
  <line x1="896" y1="502" x2="896" y2="572" stroke="#0f2744" stroke-width="0.8"/>
  <text x="910" y="515" fill="#64748b" font-size="8">Q eau</text>
  <text{sid("qcond2-val")} x="910" y="530" fill="#38bdf8" font-size="11" font-weight="700">{q_cond:.0f}</text>
  <text x="910" y="542" fill="#64748b" font-size="7.5">T/h</text>
  <text x="859" y="570" fill="#1e3a5f" font-size="7"
        text-anchor="middle">Δh = ṁ × (h_in − h_out) → Eau chaude recyclée</text>

  <!-- ════ ARBRE TURBINE → RÉDUCTEUR ════ -->
  <line x1="725" y1="248" x2="785" y2="248"
        stroke="#3b82f6" stroke-width="6" stroke-dasharray="8,5" class="flow-hp"/>
  {_instrument_circle(755, 248, "ST", "#60a5fa")}
  {tag_spd}

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
      <line x1="-14" y1="-14" x2="-10" y2="-10" stroke="#10b981" stroke-width="2"/>
      <line x1="10" y1="10" x2="14" y2="14" stroke="#10b981" stroke-width="2"/>
      <line x1="10" y1="-14" x2="14" y2="-10" stroke="#10b981" stroke-width="2"/>
      <line x1="-14" y1="10" x2="-10" y2="14" stroke="#10b981" stroke-width="2"/>
    </g>
  </g>
  <text x="835" y="283" fill="#34d399" font-size="9" text-anchor="middle">÷ 4.29</text>
  <text x="835" y="296" fill="#10b981" font-size="10" font-weight="700"
        text-anchor="middle">→ 1500 RPM</text>
  <text{sid("freq-val")} x="835" y="308" fill="#34d399" font-size="9" font-weight="700" text-anchor="middle">{freq:.2f} <tspan fill="#064e3b" font-size="8">Hz · 2 pôles</tspan></text>

  <!-- Arbre Réducteur → Alternateur -->
  <line x1="885" y1="248" x2="945" y2="248"
        stroke="#10b981" stroke-width="6" stroke-dasharray="8,5" class="flow-hp"/>
  {_instrument_circle(915, 248, "ST", "#10b981")}
  {tag_vit2}

  <!-- ════ ALTERNATEUR ════ -->
  <rect id="syn-alt-rect" x="945" y="155" width="165" height="200" rx="12"
        fill="#060d1a" stroke="{alt_col}" stroke-width="2"
        filter="url(#{'gr' if alm_pow else 'gg'})"/>
  <text x="1027" y="178" fill="#f8fafc" font-size="11" font-weight="700"
        text-anchor="middle" letter-spacing="1">ALTERNATEUR</text>
  <text x="1027" y="192" fill="#475569" font-size="8"
        text-anchor="middle">IEC 60034 · Topologie Étoile</text>
  <circle cx="1027" cy="222" r="24" fill="rgba(16,185,129,0.08)"
          stroke="{alt_col}" stroke-width="1.5"/>
  <text{sid("alt-tilde")} x="1027" y="231" fill="{alt_col}" font-size="22" text-anchor="middle"
        class="{'pulse' if alm_pow else ''}">~</text>

  <!-- Grid valeurs alternateur -->
  <rect x="952" y="254" width="152" height="96" rx="4"
        fill="rgba(15,23,42,0.75)" stroke="#0f2744" stroke-width="0.8"/>
  <text x="965" y="269" fill="#64748b" font-size="7.5">P activ.</text>
  <text{sid("power-val")} x="965" y="283" fill="{'#ef4444' if alm_pow else alt_col}" font-size="13" font-weight="700">{power:.1f}</text>
  <text x="965" y="294" fill="#64748b" font-size="7">MW</text>
  <line x1="1006" y1="256" x2="1006" y2="348" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1014" y="269" fill="#64748b" font-size="7.5">Q réact.</text>
  <text{sid("qmvar-val")} x="1014" y="283" fill="#818cf8" font-size="13" font-weight="700">{q_mvar:.1f}</text>
  <text x="1014" y="294" fill="#64748b" font-size="7">MVAR</text>
  <line x1="1058" y1="256" x2="1058" y2="348" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1065" y="269" fill="#64748b" font-size="7.5">S appar.</text>
  <text{sid("smva-val")} x="1065" y="283" fill="#fbbf24" font-size="13" font-weight="700">{s_mva:.1f}</text>
  <text x="1065" y="294" fill="#64748b" font-size="7">MVA</text>
  <line x1="954" y1="302" x2="1102" y2="302" stroke="#0f2744" stroke-width="0.8"/>
  <text x="965" y="316" fill="#64748b" font-size="7.5">cos φ</text>
  <text{sid("pf-val")} x="965" y="332" fill="{'#ef4444' if alm_pf else '#fbbf24'}" font-size="12" font-weight="700">{pf:.3f}</text>
  <text x="1014" y="316" fill="#64748b" font-size="7.5">Courant</text>
  <text{sid("ia-val")} x="1014" y="332" fill="{'#ef4444' if alm_ia else '#10b981'}" font-size="12" font-weight="700">{i_a:.0f}<tspan fill="#64748b" font-size="7"> A</tspan></text>
  <text x="1065" y="316" fill="#64748b" font-size="7.5">Tension</text>
  <text{sid("volt-val")} x="1065" y="332" fill="#10b981" font-size="12" font-weight="700">{voltage:.1f}<tspan fill="#64748b" font-size="7"> kV</tspan></text>

  <!-- ════ BUS BARRES ÉLECTRIQUE ════ -->
  <line x1="1110" y1="248" x2="1175" y2="248"
        stroke="#10b981" stroke-width="10" class="flow-el"/>
  {tag_pout}
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
  <path d="M1265,225 Q1280,235 1295,225" fill="none" stroke="#10b981" stroke-width="1"/>
  <path d="M1295,225 Q1310,235 1325,225" fill="none" stroke="#10b981" stroke-width="1"/>
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
  <text x="80" y="512" fill="#475569" font-size="8"
        text-anchor="middle">64 T/h (démarrage)</text>
  <line x1="143" y1="472" x2="385" y2="358"
        stroke="#38bdf8" stroke-width="2" stroke-dasharray="4,4" opacity="0.4"/>
  <text x="240" y="442" fill="#38bdf8" font-size="8" opacity="0.6">
    (démarrage uniquement)
  </text>

</svg>"""

    # Correction Dash : id ne doit pas être None
    div_kwargs = {"id": "gta-synoptic-inner"} if static_ids else {}

    return html.Div(
        [dash_dangerously_set_inner_html.DangerouslySetInnerHTML(svg)],
        style={
            "width":        "100%",
            "height":       "660px",
            "background":   "#060d1a",
            "overflowX":    "hidden",
            "overflowY":    "hidden",
            "borderRadius": "10px",
            "border":       "1px solid #0f2744",
            "padding":      "6px",
        },
        **div_kwargs
    )


# ── Helpers internes (utilisés aussi par la version dynamique via import) ─────
def _tag(x, y, label, value, unit, alarm=False, anchor="middle", w=90):
    """Version dynamique sans ID — pour la page Simulation."""
    val_color = "#ef4444" if alarm else "#e2e8f0"
    bkg       = "rgba(239,68,68,0.12)" if alarm else "rgba(15,23,42,0.75)"
    border    = "#ef4444" if alarm else "#1e3a5f"
    xi = x - w//2 if anchor == "middle" else x
    xt = x if anchor == "middle" else x + w//2
    return f"""
    <g>
      <rect x="{xi}" y="{y}" width="{w}" height="34"
            rx="4" fill="{bkg}" stroke="{border}" stroke-width="0.8"/>
      <text x="{xt}" y="{y+11}"
            fill="#64748b" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{label}</text>
      <text x="{xt}" y="{y+25}"
            fill="{val_color}" font-size="12" font-weight="700" text-anchor="middle"
            font-family="Share Tech Mono">{value} <tspan fill="#64748b" font-size="9" font-weight="400">{unit}</tspan></text>
    </g>"""


def _valve_symbol(cx, cy, pct, target, name, col, size=18, orient="top"):
    """Version dynamique sans ID — pour la page Simulation."""
    if orient == "right":
        actuator = f"""
        <line x1="{cx+size}" y1="{cy}" x2="{cx+size+10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx+size+10} {cy-size+2} Q {cx+size+18} {cy} {cx+size+10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text x="{cx+size+22}" y="{cy-8}" fill="#94a3b8" font-size="7.5" text-anchor="start" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    elif orient == "left":
        actuator = f"""
        <line x1="{cx-size}" y1="{cy}" x2="{cx-size-10}" y2="{cy}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size-10} {cy-size+2} Q {cx-size-18} {cy} {cx-size-10} {cy+size-2} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text x="{cx-size-22}" y="{cy-8}" fill="#94a3b8" font-size="7.5" text-anchor="end" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'
    else:
        actuator = f"""
        <line x1="{cx}" y1="{cy-size}" x2="{cx}" y2="{cy-size-5}" stroke="{col}" stroke-width="2"/>
        <path d="M {cx-size+2} {cy-size-5} Q {cx} {cy-size-12} {cx+size-2} {cy-size-5} Z" fill="{col}" opacity="0.3" stroke="{col}" stroke-width="1"/>
        """
        tgt_txt = f'<text x="{cx}" y="{cy-size-12}" fill="#94a3b8" font-size="7.5" text-anchor="middle" font-family="Share Tech Mono">Cible: {target:.0f}%</text>'

    return f"""
    {tgt_txt}
    {actuator}
    <circle cx="{cx}" cy="{cy}" r="{size}" fill="#0a101a" stroke="{col}" stroke-width="2"/>
    <text x="{cx}" y="{cy-1}" fill="{col}" font-size="9" font-weight="700" text-anchor="middle" font-family="Share Tech Mono">{name}</text>
    <text x="{cx}" y="{cy+9}" fill="{col}" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{pct:.0f}%</text>"""