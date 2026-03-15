"""
calibration/calibrate_physics.py — Calibrage des coefficients du modèle physique

Stratégie hybride (deux étapes) :
  1. STRUCTURE  : dataset UCI CCPP (Combined Cycle Power Plant, UCI Repository)
                  → calibre les relations T/P/débit → puissance / rendement
  2. ANCRAGE    : specs nominales du GTA (60 bar, 486°C, 120 T/h → 24 MW, η=92%)
                  → recale les coefficients absolus sur le GTA spécifique

Le résultat est un fichier physics_coeffs.json chargé automatiquement par PhysicsModel.

Usage :
    python -m calibration.calibrate_physics

Dépendances : pandas, numpy, scikit-learn (déjà dans requirements.txt)
"""

import os
import json
import math
import urllib.request
import zipfile
import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_percentage_error

from core.config import (
    NOMINAL, CALIBRATION_DATASET, CALIBRATION_COEFFS,
    T_HP_DESIGN, T_HP_OPERATING, AI_MODELS_DIR
)

logger = logging.getLogger("gta.calibration")

# ─────────────────────────────────────────────
# ÉTAPE 1 — TÉLÉCHARGEMENT UCI CCPP
# ─────────────────────────────────────────────

CCPP_URL = (
    "https://archive.ics.uci.edu/ml/machine-learning-databases/"
    "00294/CCPP.zip"
)
CCPP_CACHE = CALIBRATION_DATASET   # data/ccpp_dataset.csv


def download_ccpp(force: bool = False) -> pd.DataFrame:
    """
    Télécharge et met en cache le dataset UCI CCPP.

    Colonnes originales :
      AT   — Temperature ambiante (°C)
      V    — Vide d'échappement (cm Hg)  ← proxy pression condenseur
      AP   — Pression atmosphérique (mbar)
      RH   — Humidité relative (%)
      PE   — Puissance nette produite (MW)  ← variable cible

    9568 points, centrale à cycle combiné vapeur-gaz.
    """
    os.makedirs(os.path.dirname(CCPP_CACHE), exist_ok=True)

    if os.path.exists(CCPP_CACHE) and not force:
        logger.info(f"Dataset CCPP déjà en cache : {CCPP_CACHE}")
        return pd.read_csv(CCPP_CACHE)

    logger.info("Téléchargement UCI CCPP dataset…")
    zip_path = CCPP_CACHE.replace(".csv", ".zip")

    try:
        urllib.request.urlretrieve(CCPP_URL, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            # Chercher le fichier xlsx ou csv dans l'archive
            for name in z.namelist():
                if name.endswith(".xlsx") or name.endswith(".csv"):
                    z.extract(name, os.path.dirname(CCPP_CACHE))
                    extracted = os.path.join(os.path.dirname(CCPP_CACHE), name)
                    if name.endswith(".xlsx"):
                        df = pd.read_excel(extracted)
                    else:
                        df = pd.read_csv(extracted)
                    df.columns = ["AT", "V", "AP", "RH", "PE"]
                    df.to_csv(CCPP_CACHE, index=False)
                    logger.info(f"Dataset sauvegardé : {CCPP_CACHE} ({len(df)} lignes)")
                    os.remove(zip_path)
                    return df
    except Exception as e:
        logger.warning(f"Téléchargement CCPP échoué ({e}). Utilisation dataset synthétique.")
        return _generate_synthetic_ccpp()


def _generate_synthetic_ccpp() -> pd.DataFrame:
    """
    Génère un dataset synthétique basé sur la physique CCPP
    si le téléchargement échoue (pas de réseau, etc.).

    Reproduit les relations physiques connues du CCPP :
      PE ≈ f(AT, V, AP, RH)
      Les corrélations sont issues des publications sur ce dataset.
    """
    logger.info("Génération dataset synthétique CCPP (500 points)…")
    rng = np.random.default_rng(42)
    n   = 500

    AT = rng.uniform(2.0, 37.0, n)    # °C
    V  = rng.uniform(25.0, 81.0, n)   # cm Hg vide
    AP = rng.uniform(992.0, 1034.0, n) # mbar
    RH = rng.uniform(25.0, 100.0, n)  # %

    # Relation empirique approximée du CCPP
    PE = (480.0
          - 1.85 * AT
          - 0.25 * V
          + 0.01 * AP
          - 0.05 * RH
          + rng.normal(0, 1.5, n))
    PE = np.clip(PE, 420.0, 500.0)

    df = pd.DataFrame({"AT": AT, "V": V, "AP": AP, "RH": RH, "PE": PE})
    os.makedirs(os.path.dirname(CCPP_CACHE), exist_ok=True)
    df.to_csv(CCPP_CACHE, index=False)
    return df


# ─────────────────────────────────────────────
# ÉTAPE 2 — EXTRACTION DES RELATIONS PHYSIQUES
# ─────────────────────────────────────────────

def extract_physical_relationships(df: pd.DataFrame) -> dict:
    """
    Entraîne un modèle Ridge sur les données CCPP pour extraire :
      - Sensibilité de PE à la température (proxy pour α_temp)
      - Sensibilité de PE au vide condenseur (proxy pour η_condenseur)

    Ces sensibilités relatives sont transférables d'une turbine à l'autre
    car elles reflètent des lois thermodynamiques universelles.
    """
    df = df.dropna()
    X = df[["AT", "V", "AP", "RH"]].values
    y = df["PE"].values

    scaler = StandardScaler()
    X_sc   = scaler.fit_transform(X)

    model = Ridge(alpha=1.0)
    model.fit(X_sc, y)

    mape = mean_absolute_percentage_error(y, model.predict(X_sc))
    logger.info(f"Modèle CCPP : MAPE = {mape*100:.2f}%")

    # Coefficients normalisés → sensibilités relatives
    coefs = dict(zip(["AT", "V", "AP", "RH"], model.coef_))
    pe_mean = y.mean()

    # Sensibilité relative de PE à la température AT (normalisée)
    # On la mappe sur alpha_temp de notre PhysicsModel
    # sign négatif car PE diminue quand AT augmente
    sensitivity_temp = abs(coefs["AT"]) / pe_mean

    # Sensibilité au vide condenseur → impact sur rendement BP
    sensitivity_vacuum = abs(coefs["V"]) / pe_mean

    logger.info(f"Sensibilité T→P : {sensitivity_temp:.4f}")
    logger.info(f"Sensibilité vide→P : {sensitivity_vacuum:.4f}")

    return {
        "ccpp_sensitivity_temp":   sensitivity_temp,
        "ccpp_sensitivity_vacuum": sensitivity_vacuum,
        "ccpp_mape":               mape,
        "ccpp_n_samples":          len(df),
    }


# ─────────────────────────────────────────────
# ÉTAPE 3 — ANCRAGE SUR POINTS NOMINAUX GTA
# ─────────────────────────────────────────────

def anchor_to_gta_specs(ccpp_relations: dict) -> dict:
    """
    Recale les coefficients CCPP sur les specs connues du GTA.

    Points d'ancrage fournis par l'encadrant :
      A) T=486°C, P=60bar, Q=120T/h → P_elec=24MW, η=92%  (design)
      B) T=440°C, P=60bar, Q=120T/h → η≈88-89%            (opérationnel)

    Résout un système pour trouver eta_is_hp et alpha_temp cohérents.
    """
    from simulation.physics_model import PhysicsModel, _steam_enthalpy

    # ── Point A : condition design (486°C → 24 MW, η=92%) ──
    T_A = T_HP_DESIGN    # 486°C
    P_A = NOMINAL["pressure_hp"]        # 60 bar
    Q_A = NOMINAL["steam_flow_hp"]      # 120 T/h
    P_elec_target_A = NOMINAL["active_power"]   # 24 MW
    eta_target_A    = NOMINAL["efficiency"]     # 92%

    # ── Point B : condition opérationnelle (440°C → η≈88%) ──
    T_B    = T_HP_OPERATING   # 440°C
    eta_target_B = 88.5        # % — estimation terrain

    # ── Résolution de eta_is_hp ──
    # P = eta_is × m_dot × delta_h × eta_meca × eta_elec
    # On connaît tout sauf eta_is
    h_in_A = _steam_enthalpy(T_A, P_A)
    p_out_A = P_A * 0.08
    from simulation.physics_model import _steam_enthalpy_isentropic_out
    _, delta_h_ideal_A = _steam_enthalpy_isentropic_out(T_A, P_A, p_out_A, 1.0)

    m_dot_A = Q_A * 0.80 * 1000.0 / 3600.0   # 80% de 120 T/h → kg/s
    eta_meca = 0.975
    eta_elec = 0.985

    # Résoudre : 24 = eta_is × m_dot × delta_h × eta_meca × eta_elec
    if delta_h_ideal_A > 0:
        eta_is_hp_calibrated = (P_elec_target_A * 1e6) / (
            m_dot_A * delta_h_ideal_A * 1000.0 * eta_meca * eta_elec
        )
    else:
        eta_is_hp_calibrated = 0.82  # valeur par défaut

    eta_is_hp_calibrated = max(0.60, min(0.92, eta_is_hp_calibrated))

    # ── Résolution de alpha_temp ──
    # η(T_B) = η_ref × (1 + α × (T_B − T_A) / T_A)
    # η(T_B) / η_ref = 1 + α × (T_B − T_A) / T_A
    # α = (η(T_B)/η_ref − 1) × T_A / (T_B − T_A)
    eta_ratio = eta_target_B / eta_target_A
    if T_B != T_A:
        alpha_temp_calibrated = (eta_ratio - 1.0) * T_A / (T_B - T_A)
    else:
        alpha_temp_calibrated = 0.40  # valeur par défaut

    alpha_temp_calibrated = max(0.10, min(1.0, alpha_temp_calibrated))

    # ── Calibrage Stodola ──
    # C_stodola tel que P_bp=4.5bar à Q=120T/h, T=486°C
    T_in_K = T_A + 273.15
    q_bp   = Q_A * (1.0 - 0.20 * NOMINAL["valve_mp"] / 100.0)
    c_stodola_calibrated = (4.5 ** 2) / ((q_bp ** 2) * T_in_K)

    # ── Application de la sensibilité CCPP sur alpha ──
    # Légère pondération par la sensibilité observée dans le dataset réel
    ccpp_weight = 0.15   # 15% de poids au dataset externe, 85% aux specs GTA
    alpha_final = (
        (1 - ccpp_weight) * alpha_temp_calibrated
        + ccpp_weight * ccpp_relations["ccpp_sensitivity_temp"] * 10.0
    )
    alpha_final = max(0.10, min(1.0, alpha_final))

    coeffs = {
        "eta_is_hp":   round(eta_is_hp_calibrated, 4),
        "eta_is_bp":   round(eta_is_hp_calibrated * 0.951, 4),  # BP légèrement moins bon
        "alpha_temp":  round(alpha_final, 4),
        "c_stodola":   round(c_stodola_calibrated, 8),
        "calibrated_from": "UCI_CCPP + GTA_specs",
        "anchor_points": {
            "design":      {"T": T_HP_DESIGN,    "P_elec_MW": 24.0, "eta_pct": 92.0},
            "operational": {"T": T_HP_OPERATING, "P_elec_MW": None, "eta_pct": 88.5},
        },
        "ccpp_meta": ccpp_relations,
    }

    logger.info(f"Coefficients calibrés : {json.dumps({k:v for k,v in coeffs.items() if isinstance(v, float)}, indent=2)}")
    return coeffs


# ─────────────────────────────────────────────
# ÉTAPE 4 — VALIDATION POST-CALIBRAGE
# ─────────────────────────────────────────────

def validate_calibration(coeffs: dict) -> None:
    """
    Valide le modèle calibré sur les deux points nominaux et log les écarts.
    """
    # Sauvegarder temporairement + recharger le modèle
    os.makedirs(AI_MODELS_DIR, exist_ok=True)
    with open(CALIBRATION_COEFFS, "w") as f:
        json.dump(coeffs, f, indent=2)

    # Importer après sauvegarde pour que _load_calibration_coeffs prenne effet
    import importlib
    import simulation.physics_model as pm_module
    importlib.reload(pm_module)
    model = pm_module.PhysicsModel()

    report = model.validate_nominal()
    logger.info("=== Validation post-calibrage ===")
    for param, info in report.items():
        status = "OK" if info["ok"] else "ECART"
        logger.info(
            f"  {param:20s} : calculé={info['calculated']:8.2f} {info['unit']}"
            f" | spec={info['spec']:8.2f} | erreur={info['error_pct']:.1f}%  [{status}]"
        )


# ─────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def run_calibration(force_download: bool = False) -> dict:
    """
    Lance le pipeline complet de calibrage :
      1. Téléchargement / chargement UCI CCPP
      2. Extraction des relations physiques
      3. Ancrage sur specs GTA
      4. Sauvegarde + validation

    Retourne les coefficients calibrés.
    """
    logging.basicConfig(level=logging.INFO)
    logger.info("=== Démarrage calibrage physique GTA ===")

    df            = download_ccpp(force=force_download)
    ccpp_rel      = extract_physical_relationships(df)
    coeffs        = anchor_to_gta_specs(ccpp_rel)

    os.makedirs(AI_MODELS_DIR, exist_ok=True)
    with open(CALIBRATION_COEFFS, "w") as f:
        json.dump(coeffs, f, indent=2)
    logger.info(f"Coefficients sauvegardés : {CALIBRATION_COEFFS}")

    validate_calibration(coeffs)
    logger.info("=== Calibrage terminé ===")
    return coeffs


if __name__ == "__main__":
    run_calibration()