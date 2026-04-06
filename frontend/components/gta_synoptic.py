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


def _valve_symbol_static(cx, cy, pct, name, col, vid, size=18):
    """Symbole vanne SCADA avec IDs stables sur cercle + texte %."""
    return f"""
    <circle id="{vid}-circle" cx="{cx}" cy="{cy}" r="{size}" fill="#0a101a" stroke="{col}" stroke-width="2"/>
    <line x1="{cx-size+4}" y1="{cy-size+4}" x2="{cx+size-4}" y2="{cy+size-4}" stroke="{col}" stroke-width="1.5"/>
    <line x1="{cx+size-4}" y1="{cy-size+4}" x2="{cx-size+4}" y2="{cy+size-4}" stroke="{col}" stroke-width="1.5"/>
    <text x="{cx}" y="{cy-4}" fill="{col}" font-size="9" font-weight="700"
          text-anchor="middle" font-family="Share Tech Mono">{name}</text>
    <text id="{vid}-pct" x="{cx}" y="{cy+8}" fill="{col}" font-size="8.5" text-anchor="middle"
          font-family="Share Tech Mono">{pct:.0f}%</text>"""


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
    p_bar    = data.get("pressure_bp_barillet",  3.0)
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
    v2      = data.get("valve_v2",  100.0)
    v3      = data.get("valve_v3",  100.0)
    v_mp    = data.get("valve_mp",   50.0)
    v_bp    = data.get("valve_bp",   80.0)

    scenario = data.get("scenario")

    # ── Alarmes ──────────────────────────────────────────────────────────────
    alm_php  = _alarm(p_hp,  55, 65)
    alm_thp  = _alarm(t_hp, 420, 500)
    alm_qhp  = _alarm(q_hp, 100, 130)
    alm_spd  = _alarm(speed, 6300, 6550)
    alm_pow  = power > 30.0
    alm_pf   = _alarm(pf, 0.82, 0.86)
    alm_eff  = eff < 85.0
    alm_pbar = p_bar > 3.5
    alm_ia   = i_a > 3000

    # ── Couleurs dynamiques ───────────────────────────────────────────────────
    sc       = STATUS_COLORS.get(status, STATUS_COLORS["NORMAL"])["stroke"]
    hp_col   = "#ef4444" if alm_thp else "#f97316"
    alt_col  = "#ef4444" if alm_pow else ("#f59e0b" if power > 24 else "#10b981")
    bar_col  = "#ef4444" if alm_pbar else "#a78bfa"
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
        tag_php  = _tag_static(80,  258, "Pression",    "syn-php",  f"{p_hp:.1f}",  "bar",  alm_php)   # FIX#1 y:270→258
        tag_thp  = _tag_static(80,  296, "Température", "syn-thp",  f"{t_hp:.0f}",  "°C",   alm_thp)   # FIX#1 y:307→296
        tag_qhp  = _tag_static(185, 200, "Débit HP",    "syn-qhp",  f"{q_hp:.0f}",  "T/h",  alm_qhp, w=55)
        tag_spd  = _tag_static(755, 265, "Vit. arbre",  "syn-spd",  f"{speed:.0f}", "RPM",  alm_spd, w=55)  # FIX#2 x:755→768, y:258→264
        tag_v1   = _tag_static(330, 280, "Adm. HP",     "syn-v1t",  f"{v1:.0f}",    "%", w=60)                    # FIX#4 x:330→368
        tag_uout = _tag_static(1142,262, "U out",       "syn-uout", f"{voltage:.1f}","kV",  w=60)            # FIX#5 y:215→256
        tag_vit2 = _tag_static(915, 264, "Vit.",        "syn-vit2", "1500",          "RPM", w=55)            # FIX#3 y:258→264
    else:
        tag_php  = _tag(80,  258, "Pression",    f"{p_hp:.1f}",  "bar", alm_php)                # FIX#1
        tag_thp  = _tag(80,  296, "Température", f"{t_hp:.0f}",  "°C",  alm_thp)                # FIX#1
        tag_qhp  = _tag(185, 200, "Débit HP",    f"{q_hp:.0f}",  "T/h", alm_qhp, w=55)
        tag_spd  = _tag(755, 265, "Vit. arbre",  f"{speed:.0f}", "RPM", alarm=alm_spd, w=55)   # FIX#2
        tag_v1   = _tag(330, 280, "Adm. HP",     f"{v1:.0f}",    "%", w=60)                            # FIX#4
        tag_uout = _tag(1142,262, "U out",        f"{voltage:.1f}","kV", w=60)                   # FIX#5
        tag_vit2 = _tag(915, 264, "Vit.",         "1500",          "RPM", w=55)                  # FIX#3

    # ── Symboles vannes ───────────────────────────────────────────────────────
    if static_ids:
        vsym_v1  = _valve_symbol_static(330, 255, v1,  "V1",  vc1,  "syn-v1",  20)
        vsym_v2  = _valve_symbol_static(280, 175, v2,  "V2",  vc2,  "syn-v2",  13)
        vsym_v3  = _valve_symbol_static(280, 335, v3,  "V3",  vc3,  "syn-v3",  13)
        vsym_vmp = _valve_symbol_static(544, 62, v_mp, "VMP", vc_mp, "syn-vmp", 17)
        vsym_vbp = _valve_symbol_static(656, 415, v_bp,"VBP", vc_bp,"syn-vbp", 18)
    else:
        # Appel direct — _valve_symbol est défini dans ce même module
        vsym_v1  = _valve_symbol(330, 255, v1,  "V1",  vc1,  20)
        vsym_v2  = _valve_symbol(280, 175, v2,  "V2",  vc2,  13)
        vsym_v3  = _valve_symbol(280, 335, v3,  "V3",  vc3,  13)
        vsym_vmp = _valve_symbol(544, 62, v_mp,"VMP", vc_mp, 17)
        vsym_vbp = _valve_symbol(656, 415, v_bp,"VBP", vc_bp, 18)

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -30 1400 680"
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
  <line x1="1100" y1="16" x2="1125" y2="16" stroke="#f97316" stroke-width="4"/>
  <text x="1130" y="20" fill="#94a3b8" font-size="9">Vapeur HP</text>
  <line x1="1185" y1="16" x2="1210" y2="16" stroke="#3b82f6" stroke-width="4"/>
  <text x="1215" y="20" fill="#94a3b8" font-size="9">Vapeur BP</text>
  <line x1="1270" y1="16" x2="1295" y2="16" stroke="#a78bfa" stroke-width="4"/>
  <text x="1300" y="20" fill="#94a3b8" font-size="9">Extr. MP</text>
  <line x1="1100" y1="34" x2="1125" y2="34" stroke="#10b981" stroke-width="4"/>
  <text x="1130" y="38" fill="#94a3b8" font-size="9">Électrique</text>
  <line x1="1185" y1="34" x2="1210" y2="34" stroke="#60a5fa" stroke-width="2" stroke-dasharray="4,2"/>
  <text x="1215" y="38" fill="#94a3b8" font-size="9">Équilibrage</text>

  <!-- ════ SOURCE VAPEUR HP ════ -->
  <g filter="url(#go)">
    <rect x="18" y="195" width="125" height="160" rx="10"
          fill="#0a101a" stroke="{hp_col}" stroke-width="1.8"/>
  </g>
  <text x="80" y="218" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">SOURCE HP</text>
  <text x="80" y="233" fill="#64748b" font-size="8.5" text-anchor="middle">Unité Acide Sulfurique</text>

  <!-- Flamme animée -->
  <text{sid("hp-flame")} x="80" y="252" fill="{hp_col}" font-size="22" text-anchor="middle"
        class="{'pulse' if alm_thp else ''}">{'⚠' if alm_thp else '🔥'}</text>

  <!-- Tags source HP -->
  {tag_php}
  {tag_thp}

  <!-- ════ LIGNE HP ════ -->
  <line x1="143" y1="255" x2="195" y2="255"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"/>
  {_instrument_circle(195, 255, "FT", "#f97316")}
  {tag_qhp}
  <line x1="206" y1="255" x2="240" y2="255"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"
        class="flow-hp"/>

  <!-- ════ ESV ════ -->
  <g>
    <rect x="240" y="243" width="30" height="24" rx="4"
          fill="#0a101a" stroke="#94a3b8" stroke-width="1"/>
    <text x="255" y="257" fill="#94a3b8" font-size="8" font-weight="700"
          text-anchor="middle">ESV</text>
    <text x="255" y="266" fill="#10b981" font-size="7.5" text-anchor="middle">OPEN</text>
  </g>
  <line x1="270" y1="255" x2="300" y2="255"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"
        class="flow-hp"/>

  <!-- ════ VANNE V1 ADMISSION HP ════ -->
  {vsym_v1}
  {tag_v1}
  <line x1="350" y1="255" x2="385" y2="255"
        stroke="#f97316" stroke-width="10" class="flow-hp"/>

  <!-- V2 équilibrage haut -->
  <line x1="280" y1="245" x2="280" y2="180"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  {vsym_v2}
  <line x1="280" y1="162" x2="390" y2="162"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  <text x="330" y="155" fill="#60a5fa" font-size="8" text-anchor="middle">Équilibrage ~7%</text>

  <!-- V3 équilibrage bas -->
  <line x1="280" y1="265" x2="280" y2="330"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  {vsym_v3}
  <line x1="280" y1="348" x2="390" y2="348"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  <text x="330" y="358" fill="#60a5fa" font-size="8" text-anchor="middle">Équilibrage ~7%</text>
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
  <line x1="544" y1="130" x2="544" y2="40"
      stroke="#a78bfa" stroke-width="6" stroke-linecap="round" class="flow-bp"/>
  {_instrument_circle(544, 105, "PT", "#a78bfa")}
  {vsym_vmp}

<!-- Barillet MP -->
<rect id="syn-barillet-rect" x="480" y="-10" width="130" height="50" rx="8"
      fill="#0a101a" stroke="{bar_col}" stroke-width="1.8"/>
<text x="545" y="10" fill="#f8fafc" font-size="10" font-weight="600"
      text-anchor="middle" letter-spacing="1">BARILLET MP</text>
<text{sid("pbar-val")} x="545" y="25" fill="{bar_col}" font-size="11" font-weight="700"
      text-anchor="middle">{p_bar:.2f} <tspan fill="#64748b" font-size="8" font-weight="400">bar</tspan></text>
{'<rect x="590" y="-8" width="18" height="18" rx="9" fill="#ef4444" class="blink"/><text x="599" y="4" fill="white" font-size="9" text-anchor="middle" font-weight="700">!</text>' if alm_pbar else ''}

<!-- Sorties barillet [centre y = -10 + 50/2 = 15] -->
<line x1="480" y1="15" x2="380" y2="15" stroke="#a78bfa" stroke-width="3"/>
<text x="378" y="11" fill="#94a3b8" font-size="8" text-anchor="end">→ Acid. Sulf.</text>
<text x="378" y="23" fill="#94a3b8" font-size="8" text-anchor="end">→ Surchauffeur</text>
<line x1="610" y1="15" x2="635" y2="15" stroke="#a78bfa" stroke-width="3"/>
<text x="638" y="19" fill="#94a3b8" font-size="8">→ Réseau vapeur</text>

  <!-- ════ SORTIE BP → VANNE_BP → CONDENSEUR ════ -->
  <line x1="656" y1="390" x2="656" y2="410"
        stroke="#38bdf8" stroke-width="8" stroke-linecap="round" class="flow-bp"/>
  {vsym_vbp}
  <line x1="656" y1="433" x2="656" y2="490"
        stroke="#38bdf8" stroke-width="8" class="flow-bp"/>

  <!-- Condenseur -->
  <rect x="570" y="490" width="175" height="90" rx="10"
        fill="#060d1a" stroke="#38bdf8" stroke-width="1.8" filter="url(#gb)"/>
  <text x="657" y="513" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">CONDENSEUR</text>
  <text x="657" y="527" fill="#64748b" font-size="8.5"
        text-anchor="middle">Système à vide — Eau de Norya</text>
  <text x="585" y="547" fill="#64748b" font-size="8">P vide</text>
  <text{sid("pcond-val")} x="585" y="560" fill="#38bdf8" font-size="11" font-weight="700">{p_cond:.4f}</text>
  <text x="585" y="572" fill="#64748b" font-size="7.5">bar</text>
  <line x1="634" y1="538" x2="634" y2="578" stroke="#1e3a5f" stroke-width="0.8"/>
  <text x="645" y="547" fill="#64748b" font-size="8">T bp sortie</text>
  <text{sid("tbp-val")} x="645" y="560" fill="#38bdf8" font-size="11" font-weight="700">{t_bp:.0f}</text>
  <text x="645" y="572" fill="#64748b" font-size="7.5">°C</text>
  <line x1="695" y1="538" x2="695" y2="578" stroke="#1e3a5f" stroke-width="0.8"/>
  <text x="706" y="547" fill="#64748b" font-size="8">Q eau</text>
  <text{sid("qcond2-val")} x="706" y="560" fill="#38bdf8" font-size="11" font-weight="700">{q_cond:.0f}</text>
  <text x="706" y="572" fill="#64748b" font-size="7.5">T/h</text>

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
  <text x="835" y="306" fill="#064e3b" font-size="8.5" text-anchor="middle">50 Hz · 2 pôles</text>

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
  {tag_uout}
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


def _valve_symbol(cx, cy, pct, name, col, size=18):
    """Version dynamique sans ID — pour la page Simulation."""
    return f"""
    <circle cx="{cx}" cy="{cy}" r="{size}" fill="#0a101a" stroke="{col}" stroke-width="2"/>
    <line x1="{cx-size+4}" y1="{cy-size+4}" x2="{cx+size-4}" y2="{cy+size-4}" stroke="{col}" stroke-width="1.5"/>
    <line x1="{cx+size-4}" y1="{cy-size+4}" x2="{cx-size+4}" y2="{cy+size-4}" stroke="{col}" stroke-width="1.5"/>
    <text x="{cx}" y="{cy-4}" fill="{col}" font-size="9" font-weight="700"
          text-anchor="middle" font-family="Share Tech Mono">{name}</text>
    <text x="{cx}" y="{cy+8}" fill="{col}" font-size="8.5" text-anchor="middle"
          font-family="Share Tech Mono">{pct:.0f}%</text>"""