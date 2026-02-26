"""
ai/train_models.py — Script d'entraînement offline des 3 modèles IA
À exécuter une fois avant de lancer le serveur, ou après collecte de nouvelles données.

Usage :
    cd backend
    python -m ai.train_models              # entraîne les 3 modèles
    python -m ai.train_models --model ae   # entraîne uniquement l'autoencodeur
    python -m ai.train_models --model lstm
    python -m ai.train_models --model rul
"""

import sys
import os
import argparse
import logging
import random
import math
import numpy as np

# Ajout du répertoire parent au path pour imports relatifs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import NOMINAL, THRESHOLDS
from core.database import init_db, get_db

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("gta.train")


# ─────────────────────────────────────────────
# GÉNÉRATION DE DONNÉES SYNTHÉTIQUES
# ─────────────────────────────────────────────

def generate_nominal_data(n: int = 2000) -> list[dict]:
    """
    Génère n snapshots en régime nominal avec bruit gaussien faible (±0.5%).
    Utilisé pour entraîner l'autoencodeur et le LSTM.
    """
    data = []
    for i in range(n):
        # Légère dérive cyclique pour simuler des variations journalières
        cycle   = math.sin(2 * math.pi * i / 200) * 0.01
        sample  = {}
        for param, nom in NOMINAL.items():
            if not isinstance(nom, (int, float)):
                continue
            noise          = random.gauss(0, abs(nom) * 0.005)
            sample[param]  = round(nom * (1 + cycle) + noise, 3)
        data.append(sample)
    return data


def generate_degraded_data(n: int = 500) -> list[dict]:
    """
    Génère des données avec dégradation progressive (pour entraînement RUL).
    Simule une turbine qui se détériore sur la durée.
    """
    data = []
    for i in range(n):
        progress = i / n   # 0 → 1 (dégradation croissante)
        sample   = {}
        for param, nom in NOMINAL.items():
            if not isinstance(nom, (int, float)):
                continue
            # Dégradation : les paramètres s'éloignent progressivement du nominal
            drift         = nom * progress * 0.08 * random.choice([-1, 1])
            noise         = random.gauss(0, abs(nom) * 0.008)
            sample[param] = round(nom + drift + noise, 3)
        data.append(sample)
    return data


def generate_anomaly_data(n: int = 200) -> list[dict]:
    """
    Génère des données avec anomalies franches (pour validation de l'autoencodeur).
    Les valeurs dépassent les seuils définis.
    """
    data = []
    for _ in range(n):
        sample = {}
        # Choisir un paramètre à perturber aléatoirement
        param_to_perturb = random.choice(list(THRESHOLDS.keys()))
        for param, nom in NOMINAL.items():
            if not isinstance(nom, (int, float)):
                continue
            if param == param_to_perturb:
                # Valeur hors seuil (±15 à 30%)
                direction     = random.choice([-1, 1])
                sample[param] = round(nom * (1 + direction * random.uniform(0.15, 0.30)), 3)
            else:
                noise         = random.gauss(0, abs(nom) * 0.005)
                sample[param] = round(nom + noise, 3)
        data.append(sample)
    return data


# ─────────────────────────────────────────────
# ENTRAÎNEMENT AUTOENCODEUR
# ─────────────────────────────────────────────

def train_autoencoder():
    """Entraîne l'autoencodeur sur données nominales."""
    logger.info("═══ Entraînement Autoencodeur ═══")
    from ai.autoencoder import autoencoder

    nominal_data = generate_nominal_data(n=3000)
    logger.info(f"  Données nominales générées : {len(nominal_data)} points")

    autoencoder.train(nominal_data)
    logger.info(f"  Modèle entraîné — seuil : {autoencoder.threshold}")

    # Validation sur données anomales
    anomaly_data    = generate_anomaly_data(n=200)
    detected        = sum(1 for d in anomaly_data if autoencoder.predict(d)["is_anomaly"])
    recall          = detected / len(anomaly_data) * 100
    logger.info(f"  Validation anomalies : {detected}/{len(anomaly_data)} détectées ({recall:.1f}% recall)")

    # Validation sur données nominales (faux positifs)
    false_positives = sum(1 for d in nominal_data[:200] if autoencoder.predict(d)["is_anomaly"])
    fpr             = false_positives / 200 * 100
    logger.info(f"  Faux positifs (nominal) : {false_positives}/200 ({fpr:.1f}%)")
    logger.info("  ✅ Autoencodeur sauvegardé")


# ─────────────────────────────────────────────
# ENTRAÎNEMENT LSTM
# ─────────────────────────────────────────────

def train_lstm():
    """Entraîne le modèle LSTM sur l'historique nominal + dégradé."""
    logger.info("═══ Entraînement LSTM ═══")

    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        from tensorflow.keras.callbacks import EarlyStopping
        from core.config import LSTM_PATH, LSTM_SEQUENCE_LENGTH, LSTM_HORIZON
        import os

        FEATURES = ["pressure_hp", "temperature_hp", "active_power",
                    "turbine_speed", "power_factor"]

        # Génération des séquences d'entraînement
        all_data    = generate_nominal_data(4000) + generate_degraded_data(1000)
        matrix      = np.array([[d.get(f, 0) for f in FEATURES] for d in all_data])

        # Normalisation min-max
        data_min    = matrix.min(axis=0)
        data_max    = matrix.max(axis=0)
        data_range  = data_max - data_min + 1e-8
        matrix_norm = (matrix - data_min) / data_range

        # Construction des séquences (X, y)
        seq_len = LSTM_SEQUENCE_LENGTH
        horizon = LSTM_HORIZON
        X, y    = [], []
        for i in range(len(matrix_norm) - seq_len - horizon):
            X.append(matrix_norm[i : i + seq_len])
            y.append(matrix_norm[i + seq_len : i + seq_len + horizon])
        X, y = np.array(X), np.array(y)
        logger.info(f"  Séquences : X={X.shape}, y={y.shape}")

        # Architecture LSTM
        model = Sequential([
            LSTM(64, input_shape=(seq_len, len(FEATURES)), return_sequences=True),
            Dropout(0.2),
            LSTM(32, return_sequences=False),
            Dropout(0.2),
            Dense(horizon * len(FEATURES)),
        ])
        model.compile(optimizer="adam", loss="mse")
        logger.info(f"  Paramètres : {model.count_params():,}")

        # Entraînement
        history = model.fit(
            X, y.reshape(len(y), -1),
            epochs          = 30,
            batch_size      = 64,
            validation_split = 0.15,
            callbacks       = [EarlyStopping(patience=5, restore_best_weights=True)],
            verbose         = 1,
        )

        os.makedirs(os.path.dirname(LSTM_PATH), exist_ok=True)
        model.save(LSTM_PATH)
        # Sauvegarder les paramètres de normalisation
        np.savez(
            LSTM_PATH.replace(".h5", "_norm.npz"),
            data_min=data_min, data_max=data_max
        )
        val_loss = min(history.history.get("val_loss", [float("inf")]))
        logger.info(f"  MSE validation : {val_loss:.6f}")
        logger.info("  ✅ LSTM sauvegardé")

    except ImportError:
        logger.warning("  ⚠️  TensorFlow non installé — LSTM ignoré (fallback linéaire actif)")


# ─────────────────────────────────────────────
# ENTRAÎNEMENT XGBOOST RUL
# ─────────────────────────────────────────────

def train_xgboost_rul():
    """
    Entraîne XGBoost pour la prédiction du RUL.
    Génère des séries de dégradation avec RUL connu (label synthétique).
    """
    logger.info("═══ Entraînement XGBoost RUL ═══")

    try:
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_error
        import pickle
        from core.config import XGBOOST_PATH
        from ai.xgboost_rul import xgboost_rul as rul_model
        import os

        # Génération de N séries de dégradation
        N_SERIES   = 100
        X_all, y_all = [], []

        for serie in range(N_SERIES):
            total_life = random.randint(20, 60)   # durée de vie totale (jours simulés)
            n_points   = random.randint(20, 80)

            for step in range(n_points):
                # Position dans la vie : 0 = début, 1 = fin
                life_pos    = step / n_points
                rul_true    = total_life * (1 - life_pos)

                # Générer un historique synthétique pour ce point
                history     = []
                for _ in range(10):
                    drift   = life_pos * 0.12
                    sample  = {
                        k: NOMINAL[k] * (1 + drift * random.choice([-1, 1])
                                         + random.gauss(0, 0.005))
                        for k in NOMINAL
                        if isinstance(NOMINAL[k], (int, float))
                    }
                    history.append(sample)

                features = rul_model._compute_features(history)
                # Convertir le dict en vecteur numérique
                feat_vec = [v for k, v in features.items()
                            if k not in ("worst_param",) and isinstance(v, float)]
                X_all.append(feat_vec)
                y_all.append(rul_true)

        X_arr = np.array(X_all)
        y_arr = np.array(y_all)
        logger.info(f"  Dataset : {X_arr.shape[0]} échantillons, {X_arr.shape[1]} features")

        # Entraînement
        X_train, X_test, y_train, y_test = train_test_split(
            X_arr, y_arr, test_size=0.2, random_state=42
        )
        model = xgb.XGBRegressor(
            n_estimators  = 200,
            max_depth      = 5,
            learning_rate  = 0.05,
            subsample      = 0.8,
            random_state   = 42,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        # Évaluation
        y_pred = model.predict(X_test)
        mae    = mean_absolute_error(y_test, y_pred)
        logger.info(f"  MAE test : {mae:.2f} jours")

        # Sauvegarde
        os.makedirs(os.path.dirname(XGBOOST_PATH), exist_ok=True)
        with open(XGBOOST_PATH, "wb") as f:
            pickle.dump(model, f)
        logger.info("  ✅ XGBoost RUL sauvegardé")

    except ImportError:
        logger.warning("  ⚠️  xgboost/sklearn non installés — RUL ignoré (fallback stat. actif)")


# ─────────────────────────────────────────────
# EXPORT DONNÉES D'ENTRAÎNEMENT EN SQLite
# ─────────────────────────────────────────────

def populate_history_db(n: int = 500):
    """
    Peuple la base SQLite avec des données historiques synthétiques.
    Utile pour tester les endpoints /data/history et /data/statistics
    sans avoir fait tourner le serveur.
    """
    logger.info("═══ Population base SQLite ═══")
    from datetime import datetime, timedelta

    init_db()
    nominal_data  = generate_nominal_data(n // 2)
    degraded_data = generate_degraded_data(n // 2)
    all_data      = nominal_data + degraded_data
    random.shuffle(all_data)

    base_time = datetime.utcnow() - timedelta(hours=2)
    inserted  = 0

    with get_db() as conn:
        for i, d in enumerate(all_data):
            ts     = (base_time + timedelta(seconds=i * 5)).isoformat()
            status = "NORMAL" if i < len(nominal_data) else "DEGRADED"
            conn.execute("""
                INSERT INTO gta_history (
                    timestamp, pressure_hp, temperature_hp, steam_flow_hp,
                    pressure_bp, temperature_bp, steam_flow_bp,
                    turbine_speed, active_power, power_factor, efficiency,
                    valve_v1, valve_v2, valve_v3, status, scenario
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ts,
                d.get("pressure_hp", 60),
                d.get("temperature_hp", 486),
                d.get("steam_flow_hp", 120),
                d.get("pressure_bp", 4.5),
                d.get("temperature_bp", 226),
                d.get("steam_flow_bp", 74),
                d.get("turbine_speed", 6435),
                d.get("active_power", 24),
                d.get("power_factor", 0.85),
                d.get("efficiency", 92),
                d.get("valve_v1", 100),
                d.get("valve_v2", 100),
                d.get("valve_v3", 100),
                status,
                None,
            ))
            inserted += 1
        conn.commit()
    logger.info(f"  ✅ {inserted} points insérés en base SQLite")


# ─────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Entraînement des modèles IA — Digital Twin GTA")
    parser.add_argument(
        "--model",
        choices=["ae", "lstm", "rul", "all", "db"],
        default="all",
        help="Modèle à entraîner : ae=Autoencodeur, lstm=LSTM, rul=XGBoost, db=Peupler SQLite",
    )
    args = parser.parse_args()

    logger.info("╔══════════════════════════════════════╗")
    logger.info("║  Digital Twin GTA — Training Script  ║")
    logger.info("╚══════════════════════════════════════╝")

    if args.model in ("ae", "all"):
        train_autoencoder()

    if args.model in ("lstm", "all"):
        train_lstm()

    if args.model in ("rul", "all"):
        train_xgboost_rul()

    if args.model in ("db", "all"):
        populate_history_db(n=500)

    logger.info("✅ Entraînement terminé.")


if __name__ == "__main__":
    main()