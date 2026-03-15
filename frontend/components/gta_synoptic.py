"""
components/gta_synoptic.py
Schéma synoptique SCADA du GTA — niveau industriel.

Nouveautés vs version initiale :
  - 5 vannes : V1 (HP), V2/V3 (équilibrage), valve_mp (extraction MP), valve_bp (condenseur)
  - Tous les nouveaux paramètres : I(A), Q(MVAR), S(MVA), pressure_bp_barillet,
    steam_flow_condenser, pressure_condenser, reactive_power, apparent_power
  - Bus barres électrique triphasé
  - Séparation visuelle flux HP / MP / BP / électrique
  - Tags SCADA sur chaque mesure (étiquette + valeur + unité)
  - Indicateurs d'alarme sur chaque point de mesure
  - Température opérationnelle 440°C vs design 486°C clairement signalée
"""

from dash import html
import dash_dangerously_set_inner_html


STATUS_COLORS = {
    "NORMAL":   {"stroke": "#10b981", "glow": "rgba(16,185,129,0.25)", "label": "#10b981"},
    "DEGRADED": {"stroke": "#f59e0b", "glow": "rgba(245,158,11,0.25)",  "label": "#f59e0b"},
    "CRITICAL": {"stroke": "#ef4444", "glow": "rgba(239,68,68,0.3)",    "label": "#ef4444"},
}

def _vc(pct, hi_col="#f97316", lo_col="#ef4444"):
    """Couleur d'une vanne selon % ouverture."""
    if pct >= 75: return hi_col
    if pct >= 30: return "#f59e0b"
    return lo_col

def _alarm(val, lo, hi):
    """Retourne True si la valeur est hors plage normale."""
    return val < lo or val > hi

def _tag(x, y, label, value, unit, alarm=False, anchor="middle"):
    """Génère un tag SCADA (boîte label + valeur)."""
    val_color = "#ef4444" if alarm else "#e2e8f0"
    bkg       = "rgba(239,68,68,0.12)" if alarm else "rgba(15,23,42,0.75)"
    border    = "#ef4444" if alarm else "#1e3a5f"
    w = 90
    return f"""
    <g>
      <rect x="{x - w//2 if anchor=='middle' else x}" y="{y}" width="{w}" height="34"
            rx="4" fill="{bkg}" stroke="{border}" stroke-width="0.8"/>
      <text x="{x if anchor=='middle' else x + w//2}" y="{y+11}"
            fill="#64748b" font-size="8.5" text-anchor="middle" font-family="Share Tech Mono">{label}</text>
      <text x="{x if anchor=='middle' else x + w//2}" y="{y+25}"
            fill="{val_color}" font-size="12" font-weight="700" text-anchor="middle"
            font-family="Share Tech Mono">{value} <tspan fill="#64748b" font-size="9" font-weight="400">{unit}</tspan></text>
    </g>"""

def _valve_symbol(cx, cy, pct, name, col, size=18):
    """Symbole vanne SCADA (cercle avec indication %)."""
    return f"""
    <circle cx="{cx}" cy="{cy}" r="{size}" fill="#0a101a" stroke="{col}" stroke-width="2"/>
    <line x1="{cx-size+4}" y1="{cy-size+4}" x2="{cx+size-4}" y2="{cy+size-4}" stroke="{col}" stroke-width="1.5"/>
    <line x1="{cx+size-4}" y1="{cy-size+4}" x2="{cx-size+4}" y2="{cy+size-4}" stroke="{col}" stroke-width="1.5"/>
    <text x="{cx}" y="{cy-4}" fill="{col}" font-size="9" font-weight="700"
          text-anchor="middle" font-family="Share Tech Mono">{name}</text>
    <text x="{cx}" y="{cy+8}" fill="{col}" font-size="8.5" text-anchor="middle"
          font-family="Share Tech Mono">{pct:.0f}%</text>"""

def _instrument_circle(cx, cy, label, col="#60a5fa", r=11):
    """Cercle d'instrument de mesure (style P&ID)."""
    return f"""
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="#0a101a" stroke="{col}" stroke-width="1.2"/>
    <text x="{cx}" y="{cy+4}" fill="{col}" font-size="8" font-weight="600"
          text-anchor="middle" font-family="Share Tech Mono">{label}</text>"""


def create_gta_synoptic(data: dict) -> html.Div:
    status  = data.get("status",          "NORMAL")
    p_hp    = data.get("pressure_hp",      60.0)
    t_hp    = data.get("temperature_hp",  486.0)
    q_hp    = data.get("steam_flow_hp",   120.0)

    # BP — nouveaux paramètres
    p_bp_in  = data.get("pressure_bp_in",      4.5)
    t_bp     = data.get("temperature_bp",      226.0)
    p_bar    = data.get("pressure_bp_barillet",  3.0)
    q_cond   = data.get("steam_flow_condenser", 74.0)
    p_cond   = data.get("pressure_condenser",  0.0064)

    # Turbine
    speed   = data.get("turbine_speed",   6435.0)
    eff     = data.get("efficiency",        92.0)

    # Électrique
    power   = data.get("active_power",      24.0)
    pf      = data.get("power_factor",       0.85)
    q_mvar  = data.get("reactive_power",    21.4)
    s_mva   = data.get("apparent_power",    41.0)
    voltage = data.get("voltage",           10.5)
    i_a     = data.get("current_a",        2254.0)

    # Vannes
    v1      = data.get("valve_v1",  100.0)
    v2      = data.get("valve_v2",  100.0)
    v3      = data.get("valve_v3",  100.0)
    v_mp    = data.get("valve_mp",   50.0)
    v_bp    = data.get("valve_bp",   80.0)

    scenario = data.get("scenario")

    # ── Alarmes ──────────────────────────────────────────────────────
    alm_php  = _alarm(p_hp,  55, 65)
    alm_thp  = _alarm(t_hp, 420, 500)
    alm_qhp  = _alarm(q_hp, 100, 130)
    alm_spd  = _alarm(speed, 6300, 6550)
    alm_pow  = power > 30.0
    alm_pf   = _alarm(pf, 0.82, 0.86)
    alm_eff  = eff < 85.0
    alm_pbar = p_bar > 3.5
    alm_ia   = i_a > 3000

    # ── Couleurs dynamiques ──────────────────────────────────────────
    sc       = STATUS_COLORS.get(status, STATUS_COLORS["NORMAL"])["stroke"]
    hp_col   = "#ef4444" if alm_thp else "#f97316"
    alt_col  = "#ef4444" if alm_pow else ("#f59e0b" if power > 24 else "#10b981")
    bar_col  = "#ef4444" if alm_pbar else "#a78bfa"
    vc1      = _vc(v1,  "#f97316")
    vc2      = _vc(v2,  "#60a5fa")
    vc3      = _vc(v3,  "#60a5fa")
    vc_mp    = _vc(v_mp,"#a78bfa")
    vc_bp    = _vc(v_bp,"#3b82f6")

    # ── Animations ───────────────────────────────────────────────────
    flow_dur = f"{max(0.3, 120.0/max(1, q_hp)):.2f}s" if q_hp > 5 else "99999s"
    rpm_norm = min(max((speed - 5500)/1500, 0), 1)
    spin_dur = f"{max(0.4, 2.0 - rpm_norm*1.6):.2f}s"
    turb_cls = "vibrate" if speed > 6500 else ""

    # ── Indicateur T opérationnelle vs design ────────────────────────
    t_warn_design = t_hp < 460  # sous 460°C = on est en mode opérationnel dégradé

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 620"
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

  <!-- ════════════════════════════════════════════════════════════════
       TITRE & STATUT GLOBAL
  ════════════════════════════════════════════════════════════════ -->
  <rect x="8" y="6" width="280" height="28" rx="4"
        fill="rgba(15,23,42,0.9)" stroke="#1e3a5f" stroke-width="0.8"/>
  <text x="18" y="25" fill="#94a3b8" font-size="11">GTA — SYNOPTIQUE SCADA</text>
  <text x="230" y="25" fill="{sc}" font-size="11" font-weight="700">{status}</text>

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

  <!-- ════════════════════════════════════════════════════════════════
       BLOC SOURCE VAPEUR HP
  ════════════════════════════════════════════════════════════════ -->
  <g filter="url(#go)">
    <rect x="18" y="195" width="125" height="120" rx="10"
          fill="#0a101a" stroke="{hp_col}" stroke-width="1.8"/>
  </g>
  <text x="80" y="218" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">SOURCE HP</text>
  <text x="80" y="233" fill="#64748b" font-size="8.5" text-anchor="middle">Unité Acide Sulfurique</text>

  <!-- Flamme animée -->
  <text x="80" y="264" fill="{hp_col}" font-size="22" text-anchor="middle"
        class="{'pulse' if alm_thp else ''}">{'⚠' if alm_thp else '🔥'}</text>

  <!-- Tags source HP -->
  {_tag(80, 270, "Pression", f"{p_hp:.1f}", "bar", alm_php)}
  {_tag(80, 307, "Température", f"{t_hp:.0f}", "°C", alm_thp)}

  <!-- Indicateur T design vs opérationnel -->
  {'<rect x="18" y="315" width="125" height="16" rx="3" fill="rgba(245,158,11,0.15)" stroke="#f59e0b" stroke-width="0.6"/><text x="80" y="326" fill="#f59e0b" font-size="8" text-anchor="middle" font-family="Share Tech Mono">⚠ En dessous T design 486°C</text>' if t_warn_design else '<rect x="18" y="315" width="125" height="16" rx="3" fill="rgba(16,185,129,0.1)" stroke="#10b981" stroke-width="0.6"/><text x="80" y="326" fill="#10b981" font-size="8" text-anchor="middle" font-family="Share Tech Mono">✓ T design atteinte</text>'}

  <!-- Instrument P (cercle P&ID) -->
  {_instrument_circle(143, 255, "PT", "#f97316")}

  <!-- ════════════════════════════════════════════════════════════════
       LIGNE HP + MESURE DÉBIT
  ════════════════════════════════════════════════════════════════ -->
  <!-- Ligne HP principale -->
  <line x1="143" y1="255" x2="195" y2="255"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"/>

  <!-- Instrument débit FT -->
  {_instrument_circle(195, 255, "FT", "#f97316")}
  {_tag(195, 200, "Débit HP", f"{q_hp:.0f}", "T/h", alm_qhp)}

  <line x1="206" y1="255" x2="240" y2="255"
        stroke="#f97316" stroke-width="10" stroke-linecap="round"
        class="flow-hp"/>

  <!-- ════════════════════════════════════════════════════════════════
       ESV (vanne principale — hors scope, affichée comme ouverte)
  ════════════════════════════════════════════════════════════════ -->
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

  <!-- ════════════════════════════════════════════════════════════════
       VANNE V1 — ADMISSION HP
  ════════════════════════════════════════════════════════════════ -->
  <!-- V1 — admission HP -->
  {_valve_symbol(330, 255, v1, "V1", vc1, 20)}
  {_tag(330, 278, "Adm. HP", f"{v1:.0f}", "%")}
  <line x1="350" y1="255" x2="385" y2="255"
        stroke="#f97316" stroke-width="10" class="flow-hp"/>

  <!-- V2 équilibrage haut — départ AVANT turbine (x<385) -->
  <line x1="280" y1="245" x2="280" y2="180"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  {_valve_symbol(280, 175, v2, "V2", vc2, 13)}
  <line x1="280" y1="162" x2="390" y2="162"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  <text x="330" y="155" fill="#60a5fa" font-size="8" text-anchor="middle">Équilibrage ~7%</text>

  <!-- V3 équilibrage bas — départ AVANT turbine (x<385) -->
  <line x1="295" y1="265" x2="295" y2="345"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  {_valve_symbol(295, 350, v3, "V3", vc3, 13)}
  <line x1="295" y1="363" x2="390" y2="363"
        stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="5,3"/>
  <text x="342" y="378" fill="#60a5fa" font-size="8" text-anchor="middle">Équilibrage ~7%</text>

  <!-- ════════════════════════════════════════════════════════════════
       BLOC TURBINE — HP / MP / BP
  ════════════════════════════════════════════════════════════════ -->
  <g class="{turb_cls}">
    <rect x="385" y="130" width="340" height="260" rx="12"
          fill="#060d1a" stroke="#3b82f6" stroke-width="2" filter="url(#gb)"/>

    <!-- Titre turbine -->
    <text x="555" y="160" fill="#60a5fa" font-size="13" font-weight="700"
          text-anchor="middle" letter-spacing="2">TURBINE À VAPEUR</text>
    <text x="555" y="175" fill="#475569" font-size="9" text-anchor="middle">
      Réduction multi-étagée — HP → MP → BP
    </text>

    <!-- ── Étage HP ── -->
    <rect x="400" y="185" width="85" height="115" rx="6"
          fill="transparent" stroke="#3b82f6" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="442" y="202" fill="#93c5fd" font-size="11" font-weight="600" text-anchor="middle">HP</text>
    <!-- Blade lines — constrained within HP box (x:405-480, y:210-295) -->
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
    <text x="442" y="297" fill="#60a5fa" font-size="7.5" text-anchor="middle">{p_hp:.0f}→{p_bp_in:.1f} bar</text>

    <!-- ── Étage MP ── -->
    <rect x="502" y="185" width="85" height="115" rx="6"
          fill="transparent" stroke="#818cf8" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="544" y="202" fill="#a5b4fc" font-size="11" font-weight="600" text-anchor="middle">MP</text>
    <!-- Blade lines — constrained within MP box (x:507-582, y:210-295) -->
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
    <!-- Point d'extraction MP -->
    <circle cx="544" cy="185" r="5" fill="#a78bfa"/>
    <text x="570" y="185" fill="#a78bfa" font-size="8">Ext. MP</text>

    <!-- ── Étage BP ── -->
    <rect x="604" y="185" width="105" height="115" rx="6"
          fill="transparent" stroke="#38bdf8" stroke-width="1.2" stroke-dasharray="4,2"/>
    <text x="656" y="202" fill="#7dd3fc" font-size="11" font-weight="600" text-anchor="middle">BP</text>
    <!-- Blade lines — constrained within BP box (x:609-704, y:210-295) -->
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
    <text x="656" y="297" fill="#38bdf8" font-size="7.5" text-anchor="middle">{p_bp_in:.1f} bar · {t_bp:.0f}°C</text>

    <!-- Arbre commun -->
    <line x1="395" y1="248" x2="720" y2="248"
          stroke="#1d4ed8" stroke-width="4" stroke-dasharray="8,5" class="flow-hp" opacity="0.5"/>

    <!-- Footer turbine -->
    <rect x="395" y="308" width="330" height="62" rx="6"
          fill="rgba(10,16,26,0.85)" stroke="#1e3a5f" stroke-width="0.8"/>
    <text x="432" y="323" fill="#64748b" font-size="7.5">VITESSE</text>
    <text x="432" y="338" fill="{'#ef4444' if alm_spd else '#60a5fa'}" font-size="14" font-weight="700">{speed:.0f}</text>
    <text x="432" y="350" fill="#64748b" font-size="7">RPM</text>
    <line x1="500" y1="312" x2="500" y2="368" stroke="#1e3a5f" stroke-width="0.8"/>
    <text x="515" y="323" fill="#64748b" font-size="7.5">RENDEMENT</text>
    <text x="515" y="338" fill="{'#ef4444' if alm_eff else '#10b981'}" font-size="14" font-weight="700">{eff:.1f}</text>
    <text x="515" y="350" fill="#64748b" font-size="7">%</text>
    <line x1="580" y1="312" x2="580" y2="368" stroke="#1e3a5f" stroke-width="0.8"/>
    <text x="588" y="323" fill="#64748b" font-size="7.5">PRESS. BP</text>
    <text x="588" y="338" fill="#38bdf8" font-size="14" font-weight="700">{p_bp_in:.2f}</text>
    <text x="588" y="350" fill="#64748b" font-size="7">bar</text>
    <line x1="648" y1="312" x2="648" y2="368" stroke="#1e3a5f" stroke-width="0.8"/>
    <text x="655" y="323" fill="#64748b" font-size="7.5">Q COND.</text>
    <text x="655" y="338" fill="#38bdf8" font-size="14" font-weight="700">{q_cond:.0f}</text>
    <text x="655" y="350" fill="#64748b" font-size="7">T/h</text>
    <text x="555" y="365" fill="#1e3a5f" font-size="7" text-anchor="middle">Détente adiabatique — Δh = ṁ × (h_in − h_out)</text>
  </g>

  <!-- ════════════════════════════════════════════════════════════════
       EXTRACTION MP → VANNE_MP → BARILLET
  ════════════════════════════════════════════════════════════════ -->
  <line x1="544" y1="185" x2="544" y2="100"
        stroke="#a78bfa" stroke-width="6" stroke-linecap="round" class="flow-bp"/>
  {_instrument_circle(544, 140, "PT", "#a78bfa")}
  {_valve_symbol(544, 95, v_mp, "VMP", vc_mp, 17)}
  <line x1="544" y1="78" x2="544" y2="60"
        stroke="#a78bfa" stroke-width="6" class="flow-bp"/>

  <!-- Barillet MP -->
  <rect x="480" y="35" width="130" height="50" rx="8"
        fill="#0a101a" stroke="{bar_col}" stroke-width="1.8"/>
  <text x="545" y="55" fill="#f8fafc" font-size="10" font-weight="600"
        text-anchor="middle" letter-spacing="1">BARILLET MP</text>
  <text x="545" y="70" fill="{bar_col}" font-size="11" font-weight="700"
        text-anchor="middle">{p_bar:.2f} <tspan fill="#64748b" font-size="8" font-weight="400">bar</tspan></text>
  {'<rect x="590" y="32" width="18" height="18" rx="9" fill="#ef4444" class="blink"/><text x="599" y="44" fill="white" font-size="9" text-anchor="middle" font-weight="700">!</text>' if alm_pbar else ''}

  <!-- Sorties barillet -->
  <line x1="480" y1="55" x2="455" y2="55"
        stroke="#a78bfa" stroke-width="3"/>
  <text x="420" y="52" fill="#94a3b8" font-size="8">→ Acid. Sulf.</text>
  <text x="420" y="63" fill="#94a3b8" font-size="8">→ Surchauffeur</text>

  <line x1="610" y1="55" x2="635" y2="55"
        stroke="#a78bfa" stroke-width="3"/>
  <text x="638" y="59" fill="#94a3b8" font-size="8">→ Réseau vapeur</text>

  <!-- ════════════════════════════════════════════════════════════════
       SORTIE BP → VANNE_BP → CONDENSEUR
  ════════════════════════════════════════════════════════════════ -->
  <!-- Ligne sortie BP depuis étage BP turbine -->
  <line x1="656" y1="300" x2="656" y2="410"
        stroke="#38bdf8" stroke-width="8" stroke-linecap="round" class="flow-bp"/>

  <!-- Instrument FT et tag Q condenseur à droite de la ligne -->
  {_instrument_circle(680, 360, "FT", "#38bdf8")}
  {_tag(765, 343, "Q cond.", f"{q_cond:.0f}", "T/h")}

  {_valve_symbol(656, 415, v_bp, "VBP", vc_bp, 18)}
  <line x1="656" y1="433" x2="656" y2="490"
        stroke="#38bdf8" stroke-width="8" class="flow-bp"/>

  <!-- Condenseur -->
  <rect x="570" y="490" width="175" height="90" rx="10"
        fill="#060d1a" stroke="#38bdf8" stroke-width="1.8" filter="url(#gb)"/>
  <text x="657" y="513" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">CONDENSEUR</text>
  <text x="657" y="527" fill="#64748b" font-size="8.5"
        text-anchor="middle">Système à vide — Eau de Norya</text>

  <!-- Tags condenseur -->
  <text x="585" y="547" fill="#64748b" font-size="8">P vide</text>
  <text x="585" y="560" fill="#38bdf8" font-size="11" font-weight="700">{p_cond:.4f}</text>
  <text x="585" y="572" fill="#64748b" font-size="7.5">bar</text>

  <line x1="634" y1="538" x2="634" y2="578" stroke="#1e3a5f" stroke-width="0.8"/>

  <text x="645" y="547" fill="#64748b" font-size="8">T bp sortie</text>
  <text x="645" y="560" fill="#38bdf8" font-size="11" font-weight="700">{t_bp:.0f}</text>
  <text x="645" y="572" fill="#64748b" font-size="7.5">°C</text>

  <line x1="695" y1="538" x2="695" y2="578" stroke="#1e3a5f" stroke-width="0.8"/>

  <text x="706" y="547" fill="#64748b" font-size="8">Q eau</text>
  <text x="706" y="560" fill="#38bdf8" font-size="11" font-weight="700">{q_cond:.0f}</text>
  <text x="706" y="572" fill="#64748b" font-size="7.5">T/h</text>

  <!-- ════════════════════════════════════════════════════════════════
       ARBRE TURBINE → RÉDUCTEUR
  ════════════════════════════════════════════════════════════════ -->
  <line x1="725" y1="248" x2="785" y2="248"
        stroke="#3b82f6" stroke-width="6" stroke-dasharray="8,5" class="flow-hp"/>
  {_instrument_circle(755, 248, "ST", "#60a5fa")}
  {_tag(755, 258, "Vitesse arbre", f"{speed:.0f}", "RPM", alm_spd)}

  <!-- ════════════════════════════════════════════════════════════════
       RÉDUCTEUR
  ════════════════════════════════════════════════════════════════ -->
  <rect x="785" y="190" width="100" height="120" rx="10"
        fill="#0a101a" stroke="#10b981" stroke-width="1.8" filter="url(#gg)"/>
  <text x="835" y="212" fill="#f8fafc" font-size="10" font-weight="600"
        text-anchor="middle" letter-spacing="1">RÉDUCTEUR</text>

  <!-- Engrenages animés -->
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
  {_tag(915, 258, "Sortie réd.", "1500", "RPM")}

  <!-- ════════════════════════════════════════════════════════════════
       ALTERNATEUR
  ════════════════════════════════════════════════════════════════  <!-- Alternateur rect -->
  <rect x="945" y="155" width="165" height="200" rx="12"
        fill="#060d1a" stroke="{alt_col}" stroke-width="2"
        filter="url(#{'gr' if alm_pow else 'gg'})"/>
  <text x="1027" y="178" fill="#f8fafc" font-size="11" font-weight="700"
        text-anchor="middle" letter-spacing="1">ALTERNATEUR</text>
  <text x="1027" y="192" fill="#475569" font-size="8"
        text-anchor="middle">IEC 60034 · Topologie Étoile</text>

  <!-- Symbole ~ -->
  <circle cx="1027" cy="222" r="24" fill="rgba(16,185,129,0.08)"
          stroke="{alt_col}" stroke-width="1.5"/>
  <text x="1027" y="231" fill="{alt_col}" font-size="22" text-anchor="middle"
        class="{'pulse' if alm_pow else ''}">~</text>

  <!-- Grid valeurs alternateur (6 valeurs en 2 rangées) -->
  <rect x="952" y="254" width="152" height="96" rx="4"
        fill="rgba(15,23,42,0.75)" stroke="#0f2744" stroke-width="0.8"/>
  <!-- Rangée 1 : P, Q, S -->
  <text x="965" y="269" fill="#64748b" font-size="7.5">P activ.</text>
  <text x="965" y="283" fill="{'#ef4444' if alm_pow else alt_col}" font-size="13" font-weight="700">{power:.1f}</text>
  <text x="965" y="294" fill="#64748b" font-size="7">MW</text>
  <line x1="1006" y1="256" x2="1006" y2="348" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1014" y="269" fill="#64748b" font-size="7.5">Q réact.</text>
  <text x="1014" y="283" fill="#818cf8" font-size="13" font-weight="700">{q_mvar:.1f}</text>
  <text x="1014" y="294" fill="#64748b" font-size="7">MVAR</text>
  <line x1="1058" y1="256" x2="1058" y2="348" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1065" y="269" fill="#64748b" font-size="7.5">S appar.</text>
  <text x="1065" y="283" fill="#fbbf24" font-size="13" font-weight="700">{s_mva:.1f}</text>
  <text x="1065" y="294" fill="#64748b" font-size="7">MVA</text>
  <!-- Séparateur horizontal -->
  <line x1="954" y1="302" x2="1102" y2="302" stroke="#0f2744" stroke-width="0.8"/>
  <!-- Rangée 2 : cosφ, I, U -->
  <text x="965" y="316" fill="#64748b" font-size="7.5">cos φ</text>
  <text x="965" y="332" fill="{'#ef4444' if alm_pf else '#fbbf24'}" font-size="12" font-weight="700">{pf:.3f}</text>
  <text x="1014" y="316" fill="#64748b" font-size="7.5">Courant</text>
  <text x="1014" y="332" fill="{'#ef4444' if alm_ia else '#10b981'}" font-size="12" font-weight="700">{i_a:.0f}<tspan fill="#64748b" font-size="7"> A</tspan></text>
  <text x="1065" y="316" fill="#64748b" font-size="7.5">Tension</text>
  <text x="1065" y="332" fill="#10b981" font-size="12" font-weight="700">{voltage:.1f}<tspan fill="#64748b" font-size="7"> kV</tspan></text>

  <!-- ════════════════════════════════════════════════════════════════
       BUS BARRES ÉLECTRIQUE TRIPHASÉ
  ════════════════════════════════════════════════════════════════ -->
  <!-- Ligne de sortie alternateur -->
  <line x1="1110" y1="248" x2="1175" y2="248"
        stroke="#10b981" stroke-width="10" class="flow-el"/>
  {_tag(1142, 215, f"{power:.1f} MW", f"{voltage:.1f}", "kV")}

  <!-- Bus barres (3 lignes parallèles) -->
  <rect x="1175" y="180" width="20" height="160" rx="3"
        fill="#0a101a" stroke="#10b981" stroke-width="2"/>
  <text x="1185" y="175" fill="#10b981" font-size="8" text-anchor="middle">BB</text>
  <!-- Phase A -->
  <line x1="1178" y1="210" x2="1192" y2="210"
        stroke="#ef4444" stroke-width="3"/>
  <text x="1197" y="213" fill="#ef4444" font-size="7.5">L1</text>
  <!-- Phase B -->
  <line x1="1178" y1="248" x2="1192" y2="248"
        stroke="#f59e0b" stroke-width="3"/>
  <text x="1197" y="251" fill="#f59e0b" font-size="7.5">L2</text>
  <!-- Phase C -->
  <line x1="1178" y1="286" x2="1192" y2="286"
        stroke="#3b82f6" stroke-width="3"/>
  <text x="1197" y="289" fill="#3b82f6" font-size="7.5">L3</text>

  <!-- Connexion réseau MT -->
  <line x1="1195" y1="248" x2="1235" y2="248"
        stroke="#10b981" stroke-width="8" class="flow-el"/>

  <!-- ════════════════════════════════════════════════════════════════
       RÉSEAU MT
  ════════════════════════════════════════════════════════════════ -->
  <rect x="1235" y="165" width="140" height="175" rx="10"
        fill="#060d1a" stroke="#10b981" stroke-width="1.8" filter="url(#gg)"/>
  <text x="1305" y="190" fill="#f8fafc" font-size="11" font-weight="600"
        text-anchor="middle" letter-spacing="1">RÉSEAU MT</text>
  <text x="1305" y="204" fill="#475569" font-size="8.5"
        text-anchor="middle">10.5 kV · 50 Hz · 3φ</text>

  <!-- Pylônes stylisés -->
  <line x1="1265" y1="215" x2="1265" y2="260" stroke="#10b981" stroke-width="2"/>
  <line x1="1295" y1="215" x2="1295" y2="260" stroke="#10b981" stroke-width="2"/>
  <line x1="1325" y1="215" x2="1325" y2="260" stroke="#10b981" stroke-width="2"/>
  <line x1="1250" y1="225" x2="1340" y2="225" stroke="#10b981" stroke-width="1.5"/>
  <line x1="1255" y1="238" x2="1335" y2="238" stroke="#10b981" stroke-width="1.5"/>
  <!-- Fils catégorie -->
  <path d="M1265,225 Q1280,235 1295,225" fill="none" stroke="#10b981" stroke-width="1"/>
  <path d="M1295,225 Q1310,235 1325,225" fill="none" stroke="#10b981" stroke-width="1"/>

  <!-- Bilans charge -->
  <rect x="1244" y="272" width="122" height="58" rx="4"
        fill="rgba(15,23,42,0.8)" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1255" y="286" fill="#64748b" font-size="8">Charge site</text>
  <text x="1255" y="298" fill="#10b981" font-size="12" font-weight="700">14.0</text>
  <text x="1255" y="309" fill="#64748b" font-size="7.5">MW</text>
  <line x1="1305" y1="274" x2="1305" y2="328" stroke="#0f2744" stroke-width="0.8"/>
  <text x="1313" y="286" fill="#64748b" font-size="8">Excédent</text>
  <text x="1313" y="298" fill="#fbbf24" font-size="12" font-weight="700">{max(0, power-14):.1f}</text>
  <text x="1313" y="309" fill="#64748b" font-size="7.5">MW</text>

  <!-- Specs réseau -->
  <text x="1305" y="332" fill="#334155" font-size="8" text-anchor="middle">28 kV (1 min) · 40 kA (1 min)</text>

  <!-- ════════════════════════════════════════════════════════════════
       SOURCE VAPEUR BP (entrée démarrage — indication)
  ════════════════════════════════════════════════════════════════ -->
  <rect x="18" y="430" width="125" height="85" rx="8"
        fill="#0a101a" stroke="#38bdf8" stroke-width="1.2" opacity="0.7"/>
  <text x="80" y="452" fill="#94a3b8" font-size="10" font-weight="600"
        text-anchor="middle">SOURCE BP</text>
  <text x="80" y="465" fill="#475569" font-size="8"
        text-anchor="middle">Démarrage 5–10 min</text>
  <text x="80" y="488" fill="#38bdf8" font-size="11" font-weight="700"
        text-anchor="middle">{p_bp_in:.1f} <tspan fill="#64748b" font-size="8" font-weight="400">bar</tspan></text>
  <text x="80" y="503" fill="#38bdf8" font-size="11" font-weight="700"
        text-anchor="middle">226 <tspan fill="#64748b" font-size="8" font-weight="400">°C</tspan></text>
  <text x="80" y="512" fill="#475569" font-size="8"
        text-anchor="middle">64 T/h (démarrage)</text>

  <!-- Ligne pointillée BP source → turbine (démarrage uniquement) -->
  <line x1="143" y1="472" x2="385" y2="358"
        stroke="#38bdf8" stroke-width="2" stroke-dasharray="4,4" opacity="0.4"/>
  <text x="270" y="425" fill="#38bdf8" font-size="8" opacity="0.6">
    (démarrage uniquement)
  </text>

</svg>"""

    return html.Div(
        [dash_dangerously_set_inner_html.DangerouslySetInnerHTML(svg)],
        style={
            "width":          "100%",
            "height":         "660px",
            "background":     "#060d1a",
            "overflowX":      "hidden",
            "overflowY":      "hidden",
            "borderRadius":   "10px",
            "border":         "1px solid #0f2744",
            "padding":        "6px",
        }
    )