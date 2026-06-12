"""
config.py — Configuration centrale de la plateforme GTA
Charge les variables d'environnement et définit les constantes physiques.
Paramètres mis à jour selon spécifications industrielles réelles.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# SERVEUR
# ─────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
DEBUG    = os.getenv("DEBUG", "true").lower() == "true"

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")

# ─────────────────────────────────────────────
# REDIS
# ─────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))
REDIS_KEY_CURRENT    = "gta:current"
REDIS_KEY_SIMULATION = "gta:simulation"
REDIS_KEY_STATE      = "gta:state"

# ─────────────────────────────────────────────
# BASE DE DONNÉES
# ─────────────────────────────────────────────
SQLITE_PATH = os.getenv("SQLITE_PATH", "data/gta_history.db")

# ─────────────────────────────────────────────
# SIMULATION
# ─────────────────────────────────────────────
FAKE_API_INTERVAL_MS = int(os.getenv("FAKE_API_INTERVAL_MS", 500))
NOISE_LEVEL          = float(os.getenv("NOISE_LEVEL", 0.002))

# Marges pour le calcul du statut (StatusEnum)
WARNING_MARGIN  = 0.03   # ±3 % autour du seuil = DEGRADED
CRITICAL_MARGIN = 0.10   # ±10 % autour du seuil = CRITICAL

# TIMEZONE (Ajoute x heures aux horodatages système)
# Défaut : 1 (UTC+1 pour l'Algérie, France hiver, etc.)
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", 1))

# Paramètres dynamiques oscillations
OSCILLATION_PERIOD_S = 10.0
PF_MIN_CLAMP         = 0.70

# ─────────────────────────────────────────────
# TEMPÉRATURES DE RÉFÉRENCE (deux états opérationnels réels)
# T_DESIGN : condition nominale de conception (rendement optimal)
# T_OPERATING : condition actuelle terrain (cadence production acide élevée)
# ─────────────────────────────────────────────
T_HP_DESIGN    = 486.0   # °C — condition design, rendement référence
T_HP_OPERATING = 440.0   # °C — condition terrain actuelle

# ─────────────────────────────────────────────
# PARAMÈTRES NOMINAUX DU GTA — RÉGIME PERMANENT
# Source : spécifications industrielles fournies par l'encadrant
# ─────────────────────────────────────────────
NOMINAL = {
    # ── Vapeur haute pression (entrée turbine) ──
    "pressure_hp":      60.0,    # bar
    "temperature_hp":   440.0,   # °C  (condition design — T_HP_DESIGN)
    "steam_flow_hp":    120.0,   # T/h  débit total entrant

    # ── Vapeur basse pression (entrée depuis source externe, démarrage) ──
    "pressure_bp_in":   4.5,     # bar  (plage 4–6 bar)
    "temperature_bp":   226.0,   # °C
    "steam_flow_bp_in": 64.0,    # T/h  débit BP entrant (source acide sulfurique)

    # ── Sorties vapeur ──
    "steam_flow_condenser": 74.0,   # T/h  VP HP détendue vers condenseur (≠ bp_in)
    "pressure_bp_barillet": 3.0,    # bar  VP BP sortie vers barillet
    "pressure_condenser":   0.0064, # bar  vide condenseur (système à vide)

    # ── Bilan massique BP complet ──
    "steam_flow_barillet_in":  46.0,   # T/h → barillet (estimation)
    "steam_flow_chauffage_as": 5.0,   # T/h → chauffage eau AS (estimation)
    "steam_flow_surchauffeur": 3.0,   # T/h → surchauffeur AS (estimation)

    # ── Turbine ──
    "turbine_speed":    6435.0,  # RPM  vitesse nominale exacte

    # ── Alternateur ──
    "active_power":     24.0,    # MW   puissance active nominale
    "power_factor":     0.85,    # cos φ nominal
    "apparent_power":   28.2,    # MVA  puissance apparente (= active / cos φ)
    "apparent_power_max": 41.0,  # MVA  capacité maximale machine (IEC 60034)
    "current_nominal":  2254.0,  # A    I_min spec (correspond à S_max)
    "voltage":          10.5,    # kV   tension nominale (±5% → 9.975–11.025 kV)
    "reactive_power":   21.4,    # MVAR Q = P × tan(arccos(0.85)) ≈ 21.4

    # ── Vannes (% ouverture) ──
    # V1 : admission HP principale — pilote 80% du débit total
    # V2, V3 : équilibrage mécanique pur (~7% chacune) — N'affectent PAS le bilan thermo
    # valve_bp : sortie vapeur BP vers condenseur
    "valve_v1":   100.0,   # % ouverture V1 (100% = pleine admission)
    "valve_v2":   100.0,   # % ouverture V2 (équilibrage mécanique)
    "valve_v3":   100.0,   # % ouverture V3 (équilibrage mécanique)
    "valve_bp":   80.0,    # % ouverture vanne sortie BP condenseur (nominale ~80%)

    # ── Rendement ──
    "efficiency":   85.0,  # % rendement isentropique HP physique (η_is × 100, ∈ [0,100])

    # ── Centrale Huile Lubrification ──
    "lube_oil_press":       1.5,   # bar  pression nominale réseau huile
    "lube_oil_temp":        45.0,  # °C   T° entrée paliers (sortie refroidisseur)
    "lube_oil_temp_out":    60.0,  # °C   T° sortie paliers (drain retour)
    "lube_oil_tank_level":  80.0,  # %    niveau réservoir
    "lube_oil_filter_dp":   0.3,   # bar  ΔP filtre (alarme > 0.8)
}

# ─────────────────────────────────────────────
# POIDS DE DISTRIBUTION DU DÉBIT HP PAR VANNE
# V1 porte 80% du débit total ; V2+V3 = équilibrage (14% restant passe par les étages)
# Le débit thermodynamiquement actif est contrôlé par V1 + valve_bp
# ─────────────────────────────────────────────
VALVE_FLOW_WEIGHTS = {
    "v1": 0.80,   # répartition hydraulique réelle (80% du débit passe par V1)
    "v2": 0.07,   # équilibrage mécanique
    "v3": 0.07,   # équilibrage mécanique
    # les 6% restants = pertes / joints
}
# ─────────────────────────────────────────────
# TEMPÉRATURES DE RÉFÉRENCE
# ─────────────────────────────────────────────
T_HP_DESIGN    = 486.0   # °C — référence thermodynamique (calcul rendement)
T_HP_OPERATING = 440.0   # °C — valeur terrain actuelle

# ─────────────────────────────────────────────
# SEUILS D'ALARME (min, max) — régime permanent
# ─────────────────────────────────────────────
THRESHOLDS = {
    "apparent_power": {"min": 0.0, "max": 41.0},  # max = capacité machine
    "pressure_hp":      {"min": 55.0,    "max": 65.0},
    "temperature_hp":   {"min": 400.0,   "max": 500.0},   # min abaissé à 420 (terrain 440)
    "steam_flow_hp":    {"min": 80.0,   "max": 135.0},
    "turbine_speed":    {"min": 6200.0,  "max": 6600.0},
    "active_power":     {"min": 5.0,    "max": 30.0},     # max 32 MW spec
    "power_factor":     {"min": 0.80,    "max": 0.88},     # plage réelle 0.82–0.86
    "efficiency":       {"min": 55.0,    "max": 95.0},   # η_is HP physique    
    "pressure_bp_in":   {"min": 3.5,     "max": 6.5},
    "temperature_bp":   {"min": 180.0,   "max": 280.0},
    "voltage":          {"min": 9.975,   "max": 11.025},   # ±5% de 10.5 kV
    "current_a":        {"min": 0.0,     "max": 3500.0},
    "pressure_bp_barillet": {"min": 2.5, "max": 5.0},    # bar — recalibré à 5.0 pour éviter fausses alertes synchro
}

# ─────────────────────────────────────────────
# MODÈLES IA
# ─────────────────────────────────────────────
AI_MODELS_DIR         = os.getenv("AI_MODELS_DIR", "ai/saved_models")
AUTOENCODER_PATH      = os.path.join(AI_MODELS_DIR, "autoencoder.h5")
LSTM_PATH             = os.path.join(AI_MODELS_DIR, "lstm_model.h5")
XGBOOST_PATH          = os.path.join(AI_MODELS_DIR, "xgboost_rul.pkl")
AUTOENCODER_THRESHOLD = float(os.getenv("AUTOENCODER_THRESHOLD", 1.0))
LSTM_SEQUENCE_LENGTH  = int(os.getenv("LSTM_SEQUENCE_LENGTH", 20))
LSTM_HORIZON          = int(os.getenv("LSTM_HORIZON", 10))

AI_TRAIN_ON_STARTUP = os.getenv("AI_TRAIN_ON_STARTUP", "true").lower() == "true"

# ─────────────────────────────────────────────
# CALIBRAGE PHYSIQUE
# ─────────────────────────────────────────────
CALIBRATION_DATASET = os.getenv("CALIBRATION_DATASET", "data/ccpp_dataset.csv")
CALIBRATION_COEFFS  = os.path.join(AI_MODELS_DIR, "physics_coeffs.json")

# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# COEFFICIENTS PHYSIQUES — RENDEMENTS ISENTROPIQUES
#
# η_is ∈ [0, 1] par définition (Δh_réel / Δh_idéal ≤ 1).
# Calibrés sur point nominal : 24 MW @ 486°C, 60 bar, 120 T/h, V1=100%,extraction=38%
#
# Plages typiques turbines vapeur :
#   - Moderne haute efficacité   : 0.85–0.90
#   - Industrielle standard      : 0.75–0.85
#   - Charge partielle / ancienne : 0.60–0.75

# La machine GTA (41 MVA nominal) est exploitée à 24 MW (69% charge) pour protéger
# la pression barillet BP → les η_is calibrés reflètent ce régime de charge partielle.

# PHYSICS_P_OUT_RATIO : pression inter-étage (4.5/60 = 0.075) — séparation HP / BP.
# PHYSICS_V1_FLOW_FACTOR : 1.0 (V1 pilote tout le débit thermodynamiquement actif).
# ─────────────────────────────────────────────
PHYSICS_ETA_IS_HP      = float(os.getenv("PHYSICS_ETA_IS_HP",      0.85))
PHYSICS_ETA_IS_BP      = float(os.getenv("PHYSICS_ETA_IS_BP",      0.80))
PHYSICS_V1_FLOW_FACTOR = float(os.getenv("PHYSICS_V1_FLOW_FACTOR", 1.0))
PHYSICS_P_OUT_RATIO    = float(os.getenv("PHYSICS_P_OUT_RATIO",    0.075))
# ─────────────────────────────────────────────
# TAUX D'EXTRACTION VERS BARILLET BP
# Source : spec IMACID — 46 T/h extraits sur 120 T/h débit HP → 38.3%
# L'extraction intermédiaire turbine est un prélèvement à pression fixe,
# déterminé par la conception mécanique. Pas de vanne opérateur.
# ─────────────────────────────────────────────
EXTRACTION_RATIO = float(os.getenv("EXTRACTION_RATIO", 0.38))

# ─────────────────────────────────────────────
# CONTRÔLE COMMANDE — PID & SÉQUENCES
# ─────────────────────────────────────────────
ESV_MIN_SPEED_RPM     = float(os.getenv("ESV_MIN_SPEED_RPM",     2800.0))  # RPM requis avant ouverture ESV
STEAM_FLOW_BP_NOMINAL = float(os.getenv("STEAM_FLOW_BP_NOMINAL",   64.0))  # T/h débit source BP de barrage

PID_POWER_KP      = float(os.getenv("PID_POWER_KP",  2.0))   # Gain proportionnel (MW → V1%)
PID_POWER_KI      = float(os.getenv("PID_POWER_KI",  0.5))   # Gain intégral
PID_POWER_KD      = float(os.getenv("PID_POWER_KD",  0.05))  # Gain dérivé
PID_POWER_OUT_MIN = 0.0    # V1 minimum (%)
PID_POWER_OUT_MAX = 100.0  # V1 maximum (%)

SEQUENCE_START_DURATION_S = float(os.getenv("SEQUENCE_START_DURATION_S", 120.0))  # start_turbine : 0→24 MW
SEQUENCE_STOP_DURATION_S  = float(os.getenv("SEQUENCE_STOP_DURATION_S",   90.0))  # stop_turbine  : courant→0
MW_RAMP_RATE_MW_PER_MIN   = float(os.getenv("MW_RAMP_RATE_MW_PER_MIN",    2.0))   # rampe max consigne P manuelle (ASME PTC 6 : 5-8 %/min ≈ 1.2-2 MW/min sur 24 MW)

# Délais (secondes) entre étapes en mode AUTO — tous surchargeables par env
AUTO_STEP_DELAY_BARRAGE_S  = float(os.getenv("AUTO_STEP_DELAY_BARRAGE_S",   5.0))  # PRE_CHECKS → ouvrir barrage
BARRAGE_WARMUP_MIN_S       = float(os.getenv("BARRAGE_WARMUP_MIN_S",      300.0))  # préchauffage barrage avant ESV (spec 5-10 min). En dev : BARRAGE_WARMUP_MIN_S=30
BARRAGE_WARMUP_MIN_LIMIT_S = 300.0  # 5 min — limite plancher (opérateur ne peut pas descendre en dessous)
BARRAGE_WARMUP_MAX_LIMIT_S = 600.0  # 10 min — limite plafond
PRESSURE_BP_BARRAGE_BAR    = 4.5    # pression alimentation BP barrage (auxiliaire démarrage)
AUTO_STEP_DELAY_V1_S       = float(os.getenv("AUTO_STEP_DELAY_V1_S",        3.0))  # ESV_OPENED → ouvrir V1
AUTO_STEP_DELAY_EXCITE_S   = float(os.getenv("AUTO_STEP_DELAY_EXCITE_S",    3.0))  # READY_TO_EXCITE → activer AVR
AUTO_STEP_DELAY_SYNC_ARM_S = float(os.getenv("AUTO_STEP_DELAY_SYNC_ARM_S",  5.0))  # EXCITED → armer sync
EXCITED_ARM_TIMEOUT_S      = float(os.getenv("EXCITED_ARM_TIMEOUT_S",      12.0))  # watchdog : armement forcé si gouverneur non convergé dans la fenêtre stricte

# ─────────────────────────────────────────────
# DYNAMIQUE ROTOR — Swing equation (premier ordre)
#   τ = J / D  →  constante de temps de la vitesse
#   J = 1000 kg·m²  D = 80 N·m·s/rad  →  τ ≈ 12.5 s
# ─────────────────────────────────────────────
J_INERTIA               = float(os.getenv("J_INERTIA", 400.0))  # kg·m²
D_DAMPING               = float(os.getenv("D_DAMPING",                80.0))  # N·m·s/rad
SPEED_SYNC_THRESHOLD_RPM = float(os.getenv("SPEED_SYNC_THRESHOLD_RPM",   30.0))  # RPM — fenêtre de synchronisation (±0.23 % ~ fenêtre freq ±0.1 Hz)
GRID_COUPLE_FREQ_TOL_HZ  = float(os.getenv("GRID_COUPLE_FREQ_TOL_HZ",    0.2))   # Hz — tolérance fréquence au couplage réseau (±0.2 Hz ~ ±25.7 RPM, norme synchronoscope)
SPEED_SYNC_HOLD_S        = float(os.getenv("SPEED_SYNC_HOLD_S",          5.0))  # s — durée minimum en SYNCHRONIZING avant couplage auto
TAU_GRID                 = float(os.getenv("TAU_GRID",                    3.0))  # s — constante de temps effective couplée réseau (raideur réseau)
SPEED_TRIP_THRESHOLD_RPM = float(os.getenv("SPEED_TRIP_THRESHOLD_RPM",  200.0))  # RPM — seuil perte de synchronisme → découplage auto
ROLLING_TO_STOPPED_RPM   = float(os.getenv("ROLLING_TO_STOPPED_RPM",    200.0))  # RPM — seuil ROLLING→STOPPED quand pas de débit vapeur (arrêt programmé)

# ─────────────────────────────────────────────
# PID VITESSE (ROLLING phase — Governor)
#   Sortie : cible V1 (%)  /  Entrée : erreur en RPM
# ─────────────────────────────────────────────
PID_SPEED_KP     = float(os.getenv("PID_SPEED_KP",   0.05))
PID_SPEED_KI     = float(os.getenv("PID_SPEED_KI",   0.01))
PID_SPEED_KD     = float(os.getenv("PID_SPEED_KD",   0.005))
PID_SPEED_OUT_MIN = 0.0
PID_SPEED_OUT_MAX = 100.0

# ─────────────────────────────────────────────
# PROTECTIONS AUTOMATIQUES — Seuils de déclenchement
# (distincts des THRESHOLDS d'alarme, plus stricts)
# ─────────────────────────────────────────────

# Tier 1 — TRIP (V1=0, mode MANUAL)
PROT_OVERSPEED_1_RPM     = float(os.getenv("PROT_OVERSPEED_1_RPM",    7080.0))  # 110% nominal
PROT_OVERSPEED_2_RPM     = float(os.getenv("PROT_OVERSPEED_2_RPM",    7400.0))  # 115% nominal
PROT_LUBE_OIL_PRESS_BAR  = float(os.getenv("PROT_LUBE_OIL_PRESS_BAR",   0.8))  # bar
PROT_VIB_TRIP_MMS        = float(os.getenv("PROT_VIB_TRIP_MMS",          7.1))  # mm/s  zone D ISO 10816
PROT_AXIAL_DISP_MM       = float(os.getenv("PROT_AXIAL_DISP_MM",         0.8))  # mm
PROT_BEARING_TEMP_TRIP_C = float(os.getenv("PROT_BEARING_TEMP_TRIP_C", 110.0))  # °C
PROT_PRESSURE_HP_MAX_BAR = float(os.getenv("PROT_PRESSURE_HP_MAX_BAR",  70.0))  # bar
PROT_TEMP_HP_MAX_C       = float(os.getenv("PROT_TEMP_HP_MAX_C",       510.0))  # °C
PROT_VOLTAGE_MAX_KV      = float(os.getenv("PROT_VOLTAGE_MAX_KV",      11.55))  # kV  (110%)
PROT_CURRENT_MAX_A       = float(os.getenv("PROT_CURRENT_MAX_A",       3500.0))  # A
PROT_REVERSE_POWER_MW    = float(os.getenv("PROT_REVERSE_POWER_MW",     -0.5))  # MW

# Tier 2 — DISCONNECT (GRID_CONNECTED → ROLLING)
PROT_SYNC_LOSS_RPM       = float(os.getenv("PROT_SYNC_LOSS_RPM",       200.0))  # RPM
PROT_FREQ_DEVIATION_HZ   = float(os.getenv("PROT_FREQ_DEVIATION_HZ",     1.0))  # Hz
PROT_EXCITATION_MIN_PU   = float(os.getenv("PROT_EXCITATION_MIN_PU",     0.5))  # p.u.

# Tier 3 — ALARM (sans action automatique)
PROT_VIB_ALARM_MMS       = float(os.getenv("PROT_VIB_ALARM_MMS",         4.5))  # mm/s  zone C
PROT_BEARING_TEMP_ALARM_C = float(os.getenv("PROT_BEARING_TEMP_ALARM_C",  95.0))  # °C
PROT_OIL_LEVEL_MIN_PCT   = float(os.getenv("PROT_OIL_LEVEL_MIN_PCT",    30.0))  # %
PROT_OIL_FILTER_DP_BAR   = float(os.getenv("PROT_OIL_FILTER_DP_BAR",     0.8))  # bar
PROT_VOLTAGE_MIN_KV      = float(os.getenv("PROT_VOLTAGE_MIN_KV",        9.97))  # kV  (95%)

# ─────────────────────────────────────────────
# AVR / EXCITATION — IEEE Type 1 simplifié
# Modèle : 1er ordre G(s) = K_A / (1 + T_A·s)
# Discrétisation ZOH analytique (stable pour tout dt ≥ T_A)
# ─────────────────────────────────────────────
AVR_ENABLED          = True          # False → fallback formule algébrique legacy
AVR_K_A              = float(os.getenv("AVR_K_A",    2.0))   # Gain régulateur (p.u./p.u., sans normalisation /100)
AVR_T_A              = float(os.getenv("AVR_T_A",   0.05))   # Constante de temps (s)
AVR_E_FD_MIN         = 0.5           # Saturation basse (p.u.) — évite déexcitation totale
AVR_E_FD_MAX         = 2.5           # Saturation haute (p.u.)
AVR_VOLTAGE_SETPOINT = float(os.getenv("AVR_VOLTAGE_SETPOINT", 10.5))   # kV
AVR_COSPHI_SETPOINT  = float(os.getenv("AVR_COSPHI_SETPOINT",  0.85))   # cos φ cible
AVR_Q_SENSITIVITY    = float(os.getenv("AVR_Q_SENSITIVITY",    10.0))   # MVAR par p.u. E_fd (déviation / 1.0)

# ─────────────────────────────────────────────
# PHASE 0 — A.2 : Saturation tanh sur Q réactive
# ─────────────────────────────────────────────
Q_TANH_SCALE_MVAR          = float(os.getenv("Q_TANH_SCALE_MVAR", 25.0))   # enveloppe de saturation (MVAR)

# ─────────────────────────────────────────────
# PHASE 0 — A.4 : Dégradation Weibull + compteur heures GRID
# ─────────────────────────────────────────────
DEGRADATION_ENABLED              = os.getenv("DEGRADATION_ENABLED", "true").lower() == "true"
DEGRADATION_SHAPE                = float(os.getenv("DEGRADATION_SHAPE",             2.5))     # k Weibull (>1 = usure accélérée)
DEGRADATION_SCALE_H              = float(os.getenv("DEGRADATION_SCALE_H",        8000.0))    # h, vie caractéristique
DEGRADATION_MAX_EFF_DRIFT_PCT    = float(os.getenv("DEGRADATION_MAX_EFF_DRIFT_PCT",  -3.5))  # % rendement (asymptote)
DEGRADATION_MAX_VIB_DRIFT_MMS   = float(os.getenv("DEGRADATION_MAX_VIB_DRIFT_MMS",   4.0))  # mm/s vibration (asymptote)
DEGRADATION_MAX_BEARING_DRIFT_C  = float(os.getenv("DEGRADATION_MAX_BEARING_DRIFT_C", 8.0)) # °C paliers (asymptote)
DEGRADATION_PERSIST_INTERVAL_S   = int(os.getenv("DEGRADATION_PERSIST_INTERVAL_S",   60))   # cadence sauvegarde SQLite

# ─────────────────────────────────────────────
# PHASE 1 — B.1 : Droop primaire (régulation primaire fréquence)
# ─────────────────────────────────────────────
DROOP_ENABLED      = os.getenv("DROOP_ENABLED", "true").lower() == "true"
DROOP_R            = float(os.getenv("DROOP_R",            0.04))   # 4 % statisme
DROOP_FREQ_REF_HZ  = float(os.getenv("DROOP_FREQ_REF_HZ", 50.0))   # référence réseau
DROOP_DEADBAND_HZ  = float(os.getenv("DROOP_DEADBAND_HZ",  0.02))   # bande morte anti-bruit
DROOP_MAX_DELTA_MW = float(os.getenv("DROOP_MAX_DELTA_MW",  6.0))   # saturation ±25 % P_nom

# ─────────────────────────────────────────────
# PHASE 1 — B.2 : Limiteurs AVR (OEL / UEL / SCL)
# ─────────────────────────────────────────────
AVR_OEL_THRESHOLD_PU  = float(os.getenv("AVR_OEL_THRESHOLD_PU",  2.2))    # p.u. seuil sur-excitation
AVR_OEL_TIMER_S       = float(os.getenv("AVR_OEL_TIMER_S",       10.0))   # délai inverse-time OEL
AVR_UEL_MIN_Q_RATIO   = float(os.getenv("AVR_UEL_MIN_Q_RATIO",  -0.30))   # Q/S_max plancher sous-excitation
AVR_UEL_E_FD_FLOOR_PU = float(os.getenv("AVR_UEL_E_FD_FLOOR_PU", 0.85))  # plancher E_fd UEL
AVR_SCL_THRESHOLD_A   = float(os.getenv("AVR_SCL_THRESHOLD_A", 3300.0))   # A seuil courant stator
AVR_SCL_TIMER_S       = float(os.getenv("AVR_SCL_TIMER_S",       30.0))   # délai inverse-time SCL
AVR_SCL_REDUCTION_PU  = float(os.getenv("AVR_SCL_REDUCTION_PU",   0.10))  # pu/s réduction E_fd SCL

# ─────────────────────────────────────────────
# PHASE 1 — B.3 : Désurchauffeur (Attemperator)
# ─────────────────────────────────────────────
ATTEMPERATOR_ENABLED   = os.getenv("ATTEMPERATOR_ENABLED", "true").lower() == "true"
ATTEMP_KP              = float(os.getenv("ATTEMP_KP",    0.40))   # %/°C
ATTEMP_KI              = float(os.getenv("ATTEMP_KI",    0.10))   # %/(°C·s)
ATTEMP_KD              = float(os.getenv("ATTEMP_KD",    0.02))
ATTEMP_OUT_MIN         = 0.0
ATTEMP_OUT_MAX         = 100.0
ATTEMP_T_HP_SETPOINT_C = float(os.getenv("ATTEMP_T_HP_SETPOINT_C", 440.0))  # °C (= nominal)
ATTEMP_MAX_COOLING_C   = float(os.getenv("ATTEMP_MAX_COOLING_C",    60.0))   # -60 °C à 100 % injection
ATTEMP_TAU_S           = float(os.getenv("ATTEMP_TAU_S",             8.0))   # constante thermique

# ─────────────────────────────────────────────
# PHASE 1 — B.4 : Condenseur (hotwell + groupe vide)
# ─────────────────────────────────────────────
CONDENSER_ENABLED              = os.getenv("CONDENSER_ENABLED", "true").lower() == "true"
COND_LEVEL_KP                  = float(os.getenv("COND_LEVEL_KP",   1.5))
COND_LEVEL_KI                  = float(os.getenv("COND_LEVEL_KI",   0.3))
COND_LEVEL_KD                  = float(os.getenv("COND_LEVEL_KD",   0.0))
COND_LEVEL_SETPOINT_PCT        = float(os.getenv("COND_LEVEL_SETPOINT_PCT",  50.0))
COND_LEVEL_OUT_MIN             = 0.0
COND_LEVEL_OUT_MAX             = 100.0
COND_VACUUM_KP                 = float(os.getenv("COND_VACUUM_KP",  0.8))
COND_VACUUM_KI                 = float(os.getenv("COND_VACUUM_KI",  0.2))
COND_VACUUM_KD                 = float(os.getenv("COND_VACUUM_KD",  0.05))
COND_VACUUM_SETPOINT_MBAR      = float(os.getenv("COND_VACUUM_SETPOINT_MBAR", 64.0))
COND_VACUUM_OUT_MIN            = 0.0
COND_VACUUM_OUT_MAX            = 100.0
COND_INFLOW_GAIN_PCT_PER_TH    = float(os.getenv("COND_INFLOW_GAIN_PCT_PER_TH",   0.05))
COND_PUMP_GAIN_PCT_PER_PCT     = float(os.getenv("COND_PUMP_GAIN_PCT_PER_PCT",    0.08))
COND_VACUUM_LOAD_MBAR_PER_TH   = float(os.getenv("COND_VACUUM_LOAD_MBAR_PER_TH",  0.4))
COND_VACUUM_EJECTOR_MBAR_PER_PCT = float(os.getenv("COND_VACUUM_EJECTOR_MBAR_PER_PCT", 0.5))