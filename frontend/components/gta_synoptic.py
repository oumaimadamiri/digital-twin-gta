"""
components/gta_synoptic.py
Schéma SVG interactif du Groupe Turbo-Alternateur (GTA).
Retourne un composant Dash html.Div contenant le SVG animé + overlays de valeurs.
"""
from dash import html
import dash_dangerously_set_inner_html

# Couleurs selon statut
STATUS_COLORS = {
    "NORMAL":   {"stroke": "#10b981", "glow": "rgba(16,185,129,0.2)", "label": "#10b981"},
    "DEGRADED": {"stroke": "#f59e0b", "glow": "rgba(245,158,11,0.2)", "label": "#f59e0b"},
    "CRITICAL": {"stroke": "#ef4444", "glow": "rgba(239,68,68,0.2)",  "label": "#ef4444"},
}

VALVE_COLOR = {
    "open":    "#f97316", # orange for HP
    "partial": "#f59e0b", # yellow
    "closed":  "#3b82f6", # blue
}

def _valve_color(pct: float, v_type="HP") -> str:
    if pct >= 80:   
        if v_type == "HP": return "#f97316"
        if v_type == "MP": return "#f59e0b"
        if v_type == "BP": return "#3b82f6"
    if pct >= 30:   return "#f59e0b"
    return "#ef4444"

def _status_stroke(status: str) -> str:
    return STATUS_COLORS.get(status, STATUS_COLORS["NORMAL"])["stroke"]

def create_gta_synoptic(data: dict) -> html.Div:
    """
    Crée le schéma SVG complet du GTA avec les valeurs temps réel.
    """
    status     = data.get("status",       "NORMAL")
    p_hp       = data.get("pressure_hp",   60.0)
    t_hp       = data.get("temperature_hp",486.0)
    q_hp       = data.get("steam_flow_hp", 120.0)
    p_bp       = data.get("pressure_bp",    4.6)
    t_bp       = data.get("temperature_bp",116.0)
    speed      = data.get("turbine_speed",6435.0)
    power      = data.get("active_power",  24.3)
    pf         = data.get("power_factor",  0.85)
    eff        = data.get("efficiency",    88.0)
    v1         = data.get("valve_v1",     75.0)
    v2         = data.get("valve_v2",     45.0)
    v3         = data.get("valve_v3",     62.0)
    scenario   = data.get("scenario")

    sc = _status_stroke(status) 
    vc1, vc2, vc3 = _valve_color(v1, "HP"), _valve_color(v2, "MP"), _valve_color(v3, "BP")

    rpm_norm  = min(max((speed - 5500) / 1500, 0), 1)
    spin_dur  = f"{max(0.4, 2.0 - rpm_norm * 1.6):.2f}s"

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="215 0 1045 560" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="font-family:'Inter',sans-serif;background:transparent">
  <defs>
    <!-- Filtres -->
    <filter id="glow-orange" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="6" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="glow-blue" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="glow-green" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation="6" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    
    <!-- Gradients Tuyaux -->
    <linearGradient id="pipe-hp" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#f97316"/>
      <stop offset="100%" stop-color="#fdba74"/>
    </linearGradient>

    <!-- Animation Base -->
    <style>
      .spin {{ transform-origin: center; animation: spin {spin_dur} linear infinite; }}
      @keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
      
      /* Lignes animées pour arbres et tuyaux avec flow */
      .dash-flow {{ animation: dash-flow 1s linear infinite; }}
      @keyframes dash-flow {{ to {{ stroke-dashoffset: -20; }} }}
      
      .st-mono {{ font-family: 'Share Tech Mono', monospace; }}
    </style>
  </defs>

  <!-- ── 1. LÉGENDE DU HAUT ─────────────────────────────────── -->
  <rect x="230" y="10" width="40" height="6" rx="3" fill="#f97316"/>
  <text x="280" y="16" fill="#94a3b8" font-size="11" alignment-baseline="middle">Vapeur HP</text>

  <rect x="350" y="10" width="40" height="6" rx="3" fill="#3b82f6"/>
  <text x="400" y="16" fill="#94a3b8" font-size="11" alignment-baseline="middle">Vapeur BP</text>

  <rect x="470" y="10" width="40" height="6" rx="3" fill="#10b981"/>
  <text x="520" y="16" fill="#10b981" font-size="11" alignment-baseline="middle">Énergie électrique</text>

  <!-- ── 2. BLOC VAPEUR HP (CHAUDIÈRE) ─────────────────────── -->
  <g transform="translate(230, 200)">
    <!-- Main Box -->
    <rect x="0" y="0" width="120" height="100" rx="12" fill="#0f172a" stroke="#f97316" stroke-width="2" filter="url(#glow-orange)"/>
    
    <!-- Icone Flamme -->
    <circle cx="60" cy="30" r="14" fill="rgba(249,115,22,0.15)"/>
    <text x="60" y="35" fill="#f97316" font-size="16" text-anchor="middle">🔥</text>
    
    <!-- Label -->
    <text x="60" y="55" fill="#f8fafc" font-size="12" font-weight="600" text-anchor="middle" letter-spacing="1">VAPEUR HP</text>
    
    <!-- Values -->
    <text x="60" y="75" fill="#fdba74" font-size="11" class="st-mono" font-weight="700" text-anchor="middle">{p_hp:.0f} bar · {t_hp:.0f}°C</text>
    <text x="60" y="90" fill="#f8fafc" font-size="10" class="st-mono" text-anchor="middle">{q_hp:.0f} T/h</text>
  </g>

  <!-- Ligne Vapeur HP -> V1 -->
  <line x1="350" y1="250" x2="385" y2="250" stroke="#f97316" stroke-width="12" stroke-linecap="round"/>

  <!-- Valve V1 (Cercle Orange) -->
  <g transform="translate(385, 250)">
    <circle cx="0" cy="0" r="16" fill="#0f172a" stroke="#f97316" stroke-width="2"/>
    <text x="0" y="-2" fill="#f97316" font-size="9" font-weight="700" text-anchor="middle">V1</text>
    <text x="0" y="8" fill="#f97316" font-size="8" class="st-mono" text-anchor="middle">{v1:.0f}%</text>
  </g>

  <!-- Ligne V1 -> Turbine -->
  <line x1="401" y1="250" x2="430" y2="250" stroke="#f97316" stroke-width="12" stroke-dasharray="10,4" class="dash-flow"/>

  <!-- ── 3. BLOC TURBINES (HP, MP, BP) ──────────────────────── -->
  <!-- Main Blue Box -->
  <rect x="430" y="150" width="300" height="210" rx="12" fill="#0f172a" stroke="#3b82f6" stroke-width="2" filter="url(#glow-blue)"/>
  <text x="580" y="180" fill="#60a5fa" font-size="14" font-weight="600" letter-spacing="2" text-anchor="middle">TURBINES HP · MP · BP</text>

  <!-- Sub-box HP -->
  <g transform="translate(450, 200)">
    <rect x="0" y="0" width="70" height="90" rx="4" fill="transparent" stroke="#3b82f6" stroke-width="1" stroke-dasharray="4,2"/>
    <text x="35" y="20" fill="#cbd5e1" font-size="12" font-weight="600" text-anchor="middle">HP</text>
    <!-- Diagonales Turbine -->
    <line x1="10" y1="30" x2="60" y2="60" stroke="#3b82f6" stroke-width="1"/>
    <line x1="10" y1="60" x2="60" y2="30" stroke="#3b82f6" stroke-width="1"/>
    
    <text x="35" y="75" fill="#60a5fa" font-size="9" class="st-mono" text-anchor="middle">{speed:.0f} RPM</text>
    <text x="35" y="85" fill="#f8fafc" font-size="9" class="st-mono" text-anchor="middle">η = 88%</text>
  </g>

  <!-- Sub-box MP -->
  <g transform="translate(540, 200)">
    <rect x="0" y="0" width="70" height="90" rx="4" fill="transparent" stroke="#3b82f6" stroke-width="1" stroke-dasharray="4,2"/>
    <text x="35" y="20" fill="#cbd5e1" font-size="12" font-weight="600" text-anchor="middle">MP</text>
    <!-- Diagonales Turbine -->
    <line x1="10" y1="30" x2="60" y2="60" stroke="#3b82f6" stroke-width="1"/>
    <line x1="10" y1="60" x2="60" y2="30" stroke="#3b82f6" stroke-width="1"/>
    
    <text x="35" y="75" fill="#60a5fa" font-size="9" class="st-mono" text-anchor="middle">Étage 2</text>
    <text x="35" y="85" fill="#f8fafc" font-size="9" class="st-mono" text-anchor="middle">η = 91%</text>
  </g>

  <!-- Sub-box BP -->
  <g transform="translate(630, 200)">
    <rect x="0" y="0" width="70" height="90" rx="4" fill="transparent" stroke="#3b82f6" stroke-width="1" stroke-dasharray="4,2"/>
    <text x="35" y="20" fill="#cbd5e1" font-size="12" font-weight="600" text-anchor="middle">BP</text>
    <!-- Diagonales Turbine -->
    <line x1="10" y1="30" x2="60" y2="60" stroke="#3b82f6" stroke-width="1"/>
    <line x1="10" y1="60" x2="60" y2="30" stroke="#3b82f6" stroke-width="1"/>
    
    <text x="35" y="75" fill="#60a5fa" font-size="9" class="st-mono" text-anchor="middle">Étage 3</text>
    <text x="35" y="85" fill="#f8fafc" font-size="9" class="st-mono" text-anchor="middle">η = 87%</text>
  </g>

  <!-- Arbre de transmission Turbine commun -->
  <line x1="440" y1="245" x2="720" y2="245" stroke="#3b82f6" stroke-width="3" stroke-dasharray="6,4" class="dash-flow"/>

  <!-- Boite Résumé Détente (Bas Turbine) -->
  <rect x="500" y="315" width="160" height="24" rx="12" fill="rgba(59,130,246,0.1)"/>
  <text x="580" y="328" fill="#60a5fa" font-size="9" font-weight="600" text-anchor="middle">↻ {speed:.0f} RPM · Pu = {power:.1f} MW</text>
  <text x="580" y="345" fill="#94a3b8" font-size="8" text-anchor="middle">Détente adiabatique multi-étages</text>


  <!-- ── 4. CONDENSEUR & VANNES INFÉRIEURES ─────────────────── -->
  <!-- Ligne Extraction MP (V2) -->
  <line x1="575" y1="290" x2="575" y2="380" stroke="#f59e0b" stroke-width="4"/>
  
  <g transform="translate(575, 400)">
    <circle cx="0" cy="0" r="16" fill="#0f172a" stroke="#f59e0b" stroke-width="2"/>
    <text x="0" y="-2" fill="#f59e0b" font-size="9" font-weight="700" text-anchor="middle">V2</text>
    <text x="0" y="8" fill="#f59e0b" font-size="8" class="st-mono" text-anchor="middle">{v2:.0f}%</text>
  </g>

  <!-- Ligne Sortie BP (V3) vers Condenseur -->
  <line x1="665" y1="290" x2="665" y2="430" stroke="#3b82f6" stroke-width="8"/>
  
  <g transform="translate(665, 430)">
    <circle cx="0" cy="0" r="16" fill="#0f172a" stroke="#3b82f6" stroke-width="2"/>
    <text x="0" y="-2" fill="#3b82f6" font-size="9" font-weight="700" text-anchor="middle">V3</text>
    <text x="0" y="8" fill="#3b82f6" font-size="8" class="st-mono" text-anchor="middle">{v3:.0f}%</text>
  </g>
  
  <line x1="665" y1="446" x2="665" y2="470" stroke="#3b82f6" stroke-width="8" stroke-dasharray="6,4" class="dash-flow"/>

  <!-- Condenseur Box -->
  <g transform="translate(540, 470)">
    <rect x="0" y="0" width="160" height="50" rx="8" fill="#0f172a" stroke="#3b82f6" stroke-width="2"/>
    <text x="80" y="16" fill="#f8fafc" font-size="11" font-weight="600" letter-spacing="1" text-anchor="middle">CONDENSEUR</text>
    <text x="80" y="30" fill="#60a5fa" font-size="10" class="st-mono" text-anchor="middle">{p_bp:.1f} bar · {t_bp:.0f}°C</text>
    <text x="80" y="42" fill="#94a3b8" font-size="9" text-anchor="middle">64 T/h cogénération</text>
  </g>

  <!-- ── 5. RÉDUCTEUR ───────────────────────────────────────── -->
  <!-- Arbre Transmission T -> Réducteur -->
  <line x1="730" y1="245" x2="780" y2="245" stroke="#3b82f6" stroke-width="4" stroke-dasharray="6,4" class="dash-flow"/>
  <text x="755" y="235" fill="#3b82f6" font-size="9" text-anchor="middle">Arbre</text>
  <text x="755" y="260" fill="#3b82f6" font-size="9" class="st-mono" text-anchor="middle">{speed:.0f} RPM</text>

  <!-- Réducteur Box vert -->
  <g transform="translate(780, 195)">
    <rect x="0" y="0" width="90" height="100" rx="12" fill="#0f172a" stroke="#10b981" stroke-width="2" filter="url(#glow-green)"/>
    <text x="45" y="20" fill="#f8fafc" font-size="11" font-weight="600" text-anchor="middle" letter-spacing="1">RÉDUCTEUR</text>
    
    <!-- Engrenage central -->
    <circle cx="45" cy="50" r="18" fill="transparent" stroke="#10b981" stroke-width="2"/>
    <circle cx="45" cy="50" r="6" fill="#10b981"/>
    
    <!-- Details Ratio -->
    <text x="45" y="80" fill="#34d399" font-size="9" class="st-mono" text-anchor="middle">÷ 4.29</text>
    <text x="45" y="92" fill="#10b981" font-size="9" font-weight="600" text-anchor="middle">→ 1500 RPM</text>
  </g>

  <!-- Arbre R -> A -->
  <line x1="870" y1="245" x2="920" y2="245" stroke="#10b981" stroke-width="4" stroke-dasharray="6,4" class="dash-flow"/>
  <text x="895" y="235" fill="#10b981" font-size="9" class="st-mono" font-weight="600" text-anchor="middle">1500 RPM</text>

  <!-- ── 6. ALTERNATEUR ─────────────────────────────────────── -->
  <g transform="translate(920, 175)">
    <rect x="0" y="0" width="120" height="140" rx="12" fill="#0f172a" stroke="#10b981" stroke-width="2" filter="url(#glow-green)"/>
    <text x="60" y="24" fill="#f8fafc" font-size="12" font-weight="600" text-anchor="middle" letter-spacing="1">ALTERNATEUR</text>
    
    <!-- Sine wave symbol (big green circle) -->
    <circle cx="60" cy="64" r="28" fill="rgba(16,185,129,0.1)" stroke="#10b981" stroke-width="2"/>
    <text x="60" y="72" fill="#10b981" font-size="24" text-anchor="middle">~</text>
    
    <!-- Specs -->
    <text x="60" y="106" fill="#34d399" font-size="10" class="st-mono" font-weight="700" text-anchor="middle">41 MVA · 10.5 kV</text>
    <text x="60" y="120" fill="#f8fafc" font-size="10" class="st-mono" text-anchor="middle">cos φ = {pf:.3f}</text>
    <text x="60" y="132" fill="#10b981" font-size="10" font-weight="600" text-anchor="middle">{power:.1f} MW actifs</text>
  </g>

  <!-- Ligne A -> Réseau -->
  <line x1="1040" y1="245" x2="1140" y2="245" stroke="#10b981" stroke-width="12" stroke-dasharray="10,4" class="dash-flow"/>
  <text x="1090" y="235" fill="#f8fafc" font-size="10" font-weight="600" text-anchor="middle">{power:.1f} MW</text>

  <!-- ── 7. RÉSEAU ÉLECTRIQUE ───────────────────────────────── -->
  <g transform="translate(1140, 190)">
    <rect x="0" y="0" width="100" height="110" rx="4" fill="#0f172a" stroke="#10b981" stroke-width="2" filter="url(#glow-green)"/>
    <text x="50" y="24" fill="#f8fafc" font-size="11" font-weight="600" letter-spacing="1" text-anchor="middle">RÉSEAU</text>
    <text x="50" y="38" fill="#f8fafc" font-size="11" font-weight="600" letter-spacing="1" text-anchor="middle">ÉLECTRIQUE</text>
    
    <!-- Pylones (3 lignes verticales cross horizontales) -->
    <line x1="30" y1="50" x2="30" y2="75" stroke="#10b981" stroke-width="2"/>
    <line x1="50" y1="50" x2="50" y2="75" stroke="#10b981" stroke-width="2"/>
    <line x1="70" y1="50" x2="70" y2="75" stroke="#10b981" stroke-width="2"/>
    <!-- Horizontales -->
    <line x1="20" y1="58" x2="80" y2="58" stroke="#10b981" stroke-width="2"/>
    <line x1="25" y1="68" x2="75" y2="68" stroke="#10b981" stroke-width="2"/>
    
    <text x="50" y="92" fill="#34d399" font-size="10" class="st-mono" text-anchor="middle">50 Hz · 3φ</text>
    <text x="50" y="104" fill="#94a3b8" font-size="9" text-anchor="middle">HTA - 63 kV</text>
  </g>

</svg>"""

    return html.Div(
        [dash_dangerously_set_inner_html.DangerouslySetInnerHTML(svg)],
        style={
            "width": "100%",
            "height": "630px",
            "background": "#0a101a",
            "overflowX": "hidden",
            "overflowY": "hidden",
            "borderRadius": "8px",
            "border": "1px solid #1e293b",
            "padding": "8px",
        }
    )