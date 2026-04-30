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