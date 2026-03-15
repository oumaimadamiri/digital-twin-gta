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
    "temperature_hp":   486.0,   # °C  (condition design — T_HP_DESIGN)
    "steam_flow_hp":    120.0,   # T/h  débit total entrant

    # ── Vapeur basse pression (entrée depuis source externe, démarrage) ──
    "pressure_bp_in":   4.5,     # bar  (plage 4–6 bar)
    "temperature_bp":   226.0,   # °C
    "steam_flow_bp_in": 64.0,    # T/h  débit BP entrant (source acide sulfurique)

    # ── Sorties vapeur ──
    "steam_flow_condenser": 74.0,   # T/h  VP HP détendue vers condenseur (≠ bp_in)
    "pressure_bp_barillet": 3.0,    # bar  VP BP sortie vers barillet
    "pressure_condenser":   0.0064, # bar  vide condenseur (système à vide)

    # ── Turbine ──
    "turbine_speed":    6435.0,  # RPM  vitesse nominale exacte

    # ── Alternateur ──
    "active_power":     24.0,    # MW   puissance active nominale
    "power_factor":     0.85,    # cos φ nominal
    "apparent_power":   41.0,    # MVA  puissance apparente (= active / cos φ)
    "voltage":          10.5,    # kV   tension nominale (±5% → 9.975–11.025 kV)
    "current_nominal":  2254.0,  # A    courant nominal (I_min spéc.)
    "reactive_power":   21.4,    # MVAR Q = P × tan(arccos(0.85)) ≈ 21.4

    # ── Vannes (% ouverture) ──
    # V1 : admission HP principale — pilote 80% du débit total
    # V2, V3 : équilibrage mécanique pur (~7% chacune) — N'affectent PAS le bilan thermo
    # valve_mp : extraction vapeur MP vers barillet (4ème vanne)
    # valve_bp : sortie vapeur BP vers condenseur
    "valve_v1":   100.0,   # % ouverture V1 (100% = pleine admission)
    "valve_v2":   100.0,   # % ouverture V2 (équilibrage mécanique)
    "valve_v3":   100.0,   # % ouverture V3 (équilibrage mécanique)
    "valve_mp":   50.0,    # % ouverture vanne extraction MP (nominale ~50%)
    "valve_bp":   80.0,    # % ouverture vanne sortie BP condenseur (nominale ~80%)

    # ── Rendement ──
    "efficiency":   92.0,   # % rendement thermodynamique à T_HP_DESIGN=486°C
    # À T_HP_OPERATING=440°C, le rendement est abaissé (~88–89%) via le modèle physique
}

# ─────────────────────────────────────────────
# POIDS DE DISTRIBUTION DU DÉBIT HP PAR VANNE
# V1 porte 80% du débit total ; V2+V3 = équilibrage (14% restant passe par les étages)
# Le débit thermodynamiquement actif est contrôlé par V1 + valve_mp/valve_bp
# ─────────────────────────────────────────────
VALVE_FLOW_WEIGHTS = {
    "v1": 0.80,   # 80% du débit HP total passe par V1
    # V2 et V3 ne contribuent PAS au bilan de puissance — équilibrage mécanique pur
}

# ─────────────────────────────────────────────
# SEUILS D'ALARME (min, max) — régime permanent
# ─────────────────────────────────────────────
THRESHOLDS = {
    "pressure_hp":      {"min": 55.0,    "max": 65.0},
    "temperature_hp":   {"min": 420.0,   "max": 500.0},   # min abaissé à 420 (terrain 440)
    "steam_flow_hp":    {"min": 100.0,   "max": 130.0},
    "turbine_speed":    {"min": 6300.0,  "max": 6550.0},
    "active_power":     {"min": 10.0,    "max": 32.0},     # max 32 MW spec
    "power_factor":     {"min": 0.82,    "max": 0.86},     # plage réelle 0.82–0.86
    "efficiency":       {"min": 85.0,    "max": 100.0},
    "pressure_bp_in":   {"min": 3.5,     "max": 6.0},
    "temperature_bp":   {"min": 180.0,   "max": 270.0},
    "voltage":          {"min": 9.975,   "max": 11.025},   # ±5% de 10.5 kV
    "current_a":        {"min": 0.0,     "max": 3500.0},
    # Seuil critique : dépassement 24 MW → risque surpression BP barillet
    "active_power_critical": {"warning": 24.0, "trip": 30.0},
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