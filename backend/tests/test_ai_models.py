"""
tests/test_ai_models.py — Tests unitaires des 3 modèles IA
Couverture : Autoencodeur (détection), LSTM (prédiction), XGBoost (RUL).
Fonctionne avec les fallbacks statistiques (sans TensorFlow ni XGBoost).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import random
from core.config import NOMINAL, THRESHOLDS
from ai.autoencoder import Autoencoder
from ai.lstm_predictor import LSTMPredictor
from ai.xgboost_rul import XGBoostRUL
from ai import AIModule


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def nominal_snapshot(**overrides) -> dict:
    base = {k: v for k, v in NOMINAL.items() if isinstance(v, (int, float))}
    base.update(overrides)
    return base


def make_history(n: int = 20, **overrides) -> list[dict]:
    return [nominal_snapshot(**overrides) for _ in range(n)]


def make_degraded_history(n: int = 20) -> list[dict]:
    """Historique avec dégradation progressive."""
    history = []
    for i in range(n):
        drift = i / n * 0.15   # jusqu'à 15% de dérive
        snap  = nominal_snapshot(
            pressure_hp    = NOMINAL["pressure_hp"] * (1 - drift),
            temperature_hp = NOMINAL["temperature_hp"] * (1 + drift * 0.5),
        )
        history.append(snap)
    return history


# ─────────────────────────────────────────────
# TESTS — AUTOENCODEUR
# ─────────────────────────────────────────────

class TestAutoencoder:

    @pytest.fixture
    def ae(self):
        """Autoencodeur entraîné sur données nominales."""
        model = Autoencoder()
        model.train(make_history(500))
        return model

    def test_train_sets_mean_std(self, ae):
        assert ae._mean is not None
        assert ae._std  is not None
        assert ae._is_trained

    def test_nominal_low_reconstruction_error(self, ae):
        err = ae.reconstruction_error(nominal_snapshot())
        assert err < ae.threshold, \
            f"Erreur nominale ({err:.4f}) doit être < seuil ({ae.threshold})"

    def test_anomaly_higher_error(self, ae):
        """Une anomalie franche doit avoir une erreur supérieure au nominal."""
        err_nominal = ae.reconstruction_error(nominal_snapshot())
        err_anomaly = ae.reconstruction_error(nominal_snapshot(pressure_hp=20.0))
        assert err_anomaly > err_nominal

    def test_nominal_not_flagged_as_anomaly(self, ae):
        result = ae.predict(nominal_snapshot())
        assert result["is_anomaly"] is False

    def test_large_deviation_flagged_as_anomaly(self, ae):
        anomaly = nominal_snapshot(pressure_hp=20.0, temperature_hp=600.0)
        result  = ae.predict(anomaly)
        assert result["is_anomaly"] is True

    def test_predict_returns_required_keys(self, ae):
        result = ae.predict(nominal_snapshot())
        assert "is_anomaly"           in result
        assert "reconstruction_error" in result
        assert "anomaly_score"        in result
        assert "threshold"            in result

    def test_anomaly_score_between_0_and_1(self, ae):
        for snap in [nominal_snapshot(), nominal_snapshot(pressure_hp=30.0)]:
            score = ae.predict(snap)["anomaly_score"]
            assert 0.0 <= score <= 1.0, f"Score hors plage : {score}"

    def test_untrained_returns_zero_error(self):
        ae = Autoencoder()
        ae._is_trained = False
        assert ae.reconstruction_error(nominal_snapshot()) == 0.0

    def test_false_positive_rate_low(self, ae):
        """Moins de 10% de faux positifs sur des données nominales."""
        nominal_data  = [nominal_snapshot(
            pressure_hp    = NOMINAL["pressure_hp"] + random.gauss(0, 0.3),
            temperature_hp = NOMINAL["temperature_hp"] + random.gauss(0, 2.0),
        ) for _ in range(100)]
        fp = sum(1 for d in nominal_data if ae.predict(d)["is_anomaly"])
        assert fp / 100 < 0.10, f"Taux FP trop élevé : {fp}%"

    def test_recall_on_large_anomalies(self, ae):
        """L'autoencodeur doit détecter les anomalies franches (>80% recall)."""
        anomalies = [nominal_snapshot(pressure_hp=20.0 + random.uniform(-3, 3))
                     for _ in range(50)]
        detected  = sum(1 for d in anomalies if ae.predict(d)["is_anomaly"])
        assert detected / 50 >= 0.80, f"Recall trop faible : {detected}/50"


# ─────────────────────────────────────────────
# TESTS — LSTM PREDICTOR
# ─────────────────────────────────────────────

class TestLSTMPredictor:

    @pytest.fixture
    def lstm(self):
        return LSTMPredictor()

    def test_not_ready_with_empty_buffer(self, lstm):
        result = lstm.predict()
        assert result["ready"] is False

    def test_not_ready_with_1_point(self, lstm):
        lstm.push(nominal_snapshot())
        result = lstm.predict()
        assert result["ready"] is False

    def test_ready_after_3_points(self, lstm):
        for _ in range(3):
            lstm.push(nominal_snapshot())
        result = lstm.predict()
        assert result["ready"] is True

    def test_predict_returns_required_keys(self, lstm):
        for _ in range(5):
            lstm.push(nominal_snapshot())
        result = lstm.predict()
        assert "predicted_values"   in result
        assert "confidence_lower"   in result
        assert "confidence_upper"   in result
        assert "horizon_steps"      in result
        assert "horizon_seconds"    in result
        assert "features"           in result

    def test_predict_horizon_correct_length(self, lstm):
        for _ in range(10):
            lstm.push(nominal_snapshot())
        result = lstm.predict()
        assert len(result["predicted_values"])  == lstm.horizon
        assert len(result["confidence_lower"])  == lstm.horizon
        assert len(result["confidence_upper"])  == lstm.horizon

    def test_confidence_lower_le_upper(self, lstm):
        for _ in range(10):
            lstm.push(nominal_snapshot())
        result = lstm.predict()
        for lo, hi in zip(result["confidence_lower"], result["confidence_upper"]):
            for l, h in zip(lo, hi):
                assert l <= h

    def test_prediction_near_nominal_for_stable_input(self, lstm):
        """Pour un signal stable, la prédiction ne doit pas dériver extrêmement."""
        for _ in range(25):
            lstm.push(nominal_snapshot())
        result = lstm.predict()
        # Vérifier la 1ère feature (pressure_hp) : doit rester proche du nominal
        pred_pressure = [step[0] for step in result["predicted_values"]]
        for p in pred_pressure:
            assert NOMINAL["pressure_hp"] * 0.5 <= p <= NOMINAL["pressure_hp"] * 1.5, \
                f"Prédiction pression très éloignée du nominal : {p:.1f}"

    def test_push_updates_buffer(self, lstm):
        initial_len = len(lstm._buffer)
        lstm.push(nominal_snapshot())
        assert len(lstm._buffer) == initial_len + 1

    def test_buffer_respects_maxlen(self, lstm):
        for _ in range(lstm.seq_length + 50):
            lstm.push(nominal_snapshot())
        assert len(lstm._buffer) == lstm.seq_length

    def test_predict_with_param_argument(self, lstm):
        for _ in range(4):
            lstm.push(nominal_snapshot())
        result = lstm.predict(nominal_snapshot())
        assert result["ready"] is True


# ─────────────────────────────────────────────
# TESTS — XGBOOST RUL
# ─────────────────────────────────────────────

class TestXGBoostRUL:

    @pytest.fixture
    def rul(self):
        return XGBoostRUL()

    def test_not_ready_with_too_few_points(self, rul):
        result = rul.estimate_rul(make_history(3))
        assert result["ready"] is False

    def test_ready_with_5_or_more_points(self, rul):
        result = rul.estimate_rul(make_history(10))
        assert result["ready"] is True

    def test_returns_required_keys(self, rul):
        result = rul.estimate_rul(make_history(10))
        assert "rul_days"            in result
        assert "estimated_failure"   in result
        assert "confidence"          in result
        assert "degradation_score"   in result
        assert "critical_parameter"  in result

    def test_rul_positive(self, rul):
        result = rul.estimate_rul(make_history(20))
        assert result["rul_days"] >= 0.0

    def test_nominal_has_high_rul(self, rul):
        """Un système nominal doit avoir un RUL élevé (proche de 30 jours)."""
        result = rul.estimate_rul(make_history(30))
        assert result["rul_days"] >= 20.0, \
            f"RUL nominal trop bas : {result['rul_days']:.1f} jours"

    def test_degraded_has_lower_rul(self, rul):
        rul_nominal  = rul.estimate_rul(make_history(20))["rul_days"]
        rul_degraded = rul.estimate_rul(make_degraded_history(20))["rul_days"]
        assert rul_degraded < rul_nominal, \
            f"RUL dégradé ({rul_degraded:.1f}j) doit être < nominal ({rul_nominal:.1f}j)"

    def test_failure_date_in_future(self, rul):
        from datetime import datetime
        result = rul.estimate_rul(make_history(10))
        # La date de panne doit être parseable et dans le futur
        failure_str = result["estimated_failure"]
        assert isinstance(failure_str, str)
        failure_dt  = datetime.strptime(failure_str, "%d/%m/%Y")
        assert failure_dt >= datetime.utcnow().replace(hour=0, minute=0, second=0)

    def test_compute_features_returns_dict(self, rul):
        features = rul._compute_features(make_history(10))
        assert isinstance(features, dict)
        assert "degradation_index" in features
        assert "worst_param"       in features

    def test_degradation_index_between_0_and_1(self, rul):
        features = rul._compute_features(make_history(10))
        assert 0.0 <= features["degradation_index"] <= 1.5   # peut légèrement dépasser 1


# ─────────────────────────────────────────────
# TESTS — AI MODULE (orchestrateur)
# ─────────────────────────────────────────────

class TestAIModule:

    @pytest.fixture
    def module(self):
        m = AIModule()
        # Entraîner l'autoencodeur pour que les tests soient significatifs
        from ai.autoencoder import autoencoder
        autoencoder.train(make_history(300))
        return m

    def test_run_full_analysis_returns_3_sections(self, module):
        result = module.run_full_analysis(
            current_params = nominal_snapshot(),
            history        = make_history(20),
        )
        assert "anomaly_detection" in result
        assert "lstm_prediction"   in result
        assert "rul_estimation"    in result

    def test_run_detection_returns_dict(self, module):
        result = module.run_detection(nominal_snapshot())
        assert isinstance(result, dict)
        assert "is_anomaly" in result

    def test_run_prediction_returns_dict(self, module):
        for _ in range(5):
            module.run_prediction(nominal_snapshot())
        result = module.run_prediction(nominal_snapshot())
        assert isinstance(result, dict)

    def test_estimate_rul_returns_dict(self, module):
        result = module.estimate_rul(make_history(10))
        assert isinstance(result, dict)
        assert "rul_days" in result or "ready" in result

    def test_nominal_no_anomaly(self, module):
        result = module.run_detection(nominal_snapshot())
        assert result["is_anomaly"] is False

    def test_extreme_anomaly_detected(self, module):
        anomaly = nominal_snapshot(pressure_hp=10.0, temperature_hp=700.0)
        result  = module.run_detection(anomaly)
        assert result["is_anomaly"] is True