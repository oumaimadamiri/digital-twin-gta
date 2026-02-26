"""
config.py — Configuration centrale de la plateforme GTA
Charge les variables d'environnement et définit les constantes physiques.
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

# Origines autorisées pour le CORS (liste CSV ou "*")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")

# ─────────────────────────────────────────────
# REDIS
# ─────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))
REDIS_KEY_CURRENT = "gta:current"
REDIS_KEY_SIMULATION = "gta:simulation"
REDIS_KEY_STATE   = "gta:state"

# ─────────────────────────────────────────────
# BASE DE DONNÉES
# ─────────────────────────────────────────────
SQLITE_PATH = os.getenv("SQLITE_PATH", "data/gta_history.db")

# ─────────────────────────────────────────────
# SIMULATION
# ─────────────────────────────────────────────
FAKE_API_INTERVAL_MS = int(os.getenv("FAKE_API_INTERVAL_MS", 500))
NOISE_LEVEL          = float(os.getenv("NOISE_LEVEL", 0.002))   # 0.2% de bruit gaussien (plus stable)

# ─────────────────────────────────────────────
# PARAMÈTRES NOMINAUX DU GTA
# (source : spécifications industrielles du rapport)
# ─────────────────────────────────────────────
NOMINAL = {
    # Côté vapeur haute pression
    "pressure_hp":    60.0,    # bar
    "temperature_hp": 470.0,   # °C (ajusté de 486 pour plus de marge)
    "steam_flow_hp":  120.0,   # T/h
    # Côté vapeur basse pression
    "pressure_bp":    4.5,     # bar
    "temperature_bp": 226.0,   # °C
    "steam_flow_bp":  74.0,    # T/h  (vers condenseur)
    # Turbine
    "turbine_speed":  6420.0,  # RPM (ajusté pour plus de marge par rapport au bas du range 6300-6500)
    # Alternateur
    "active_power":   24.0,    # MW
    "power_factor":   0.85,    # cos φ
    "apparent_power": 41.0,    # MVA
    "voltage":        10.5,    # kV
    # Vannes (% ouverture)
    "valve_v1":       100.0,   # % - admission HP
    "valve_v2":       100.0,   # % - extraction MP
    "valve_v3":       100.0,   # % - sortie BP
    # Rendement
    "efficiency":     92.0,    # %
}

# ─────────────────────────────────────────────
# SEUILS D'ALARME (min, max)
# ─────────────────────────────────────────────
THRESHOLDS = {
    "pressure_hp":    {"min": 55.0,   "max": 65.0},
    "temperature_hp": {"min": 440.0,  "max": 500.0},
    "steam_flow_hp":  {"min": 100.0,  "max": 130.0},
    "turbine_speed":  {"min": 6300.0, "max": 6500.0},
    "active_power":   {"min": 0.0,    "max": 32.0},
    "power_factor":   {"min": 0.80,   "max": 0.90},
    "efficiency":     {"min": 85.0,   "max": 100.0},
    "pressure_bp":    {"min": 3.5,    "max": 6.0},
    "temperature_bp": {"min": 180.0,  "max": 270.0},
}

# ─────────────────────────────────────────────
# MODÈLES IA
# ─────────────────────────────────────────────
AI_MODELS_DIR          = os.getenv("AI_MODELS_DIR", "ai/saved_models")
AUTOENCODER_PATH       = os.path.join(AI_MODELS_DIR, "autoencoder.h5")
LSTM_PATH              = os.path.join(AI_MODELS_DIR, "lstm_model.h5")
XGBOOST_PATH           = os.path.join(AI_MODELS_DIR, "xgboost_rul.pkl")
AUTOENCODER_THRESHOLD  = float(os.getenv("AUTOENCODER_THRESHOLD", 1.0))
LSTM_SEQUENCE_LENGTH   = int(os.getenv("LSTM_SEQUENCE_LENGTH", 20))
LSTM_HORIZON           = int(os.getenv("LSTM_HORIZON", 10))

# Entraîner ou non les modèles IA au démarrage de l'API
AI_TRAIN_ON_STARTUP = os.getenv("AI_TRAIN_ON_STARTUP", "true").lower() == "true"