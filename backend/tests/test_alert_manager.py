"""
tests/test_alert_manager.py — Tests unitaires du gestionnaire d'alertes
Couverture : seuils, sévérité, alertes IA, mise à jour seuils, acquittement.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from services.alert_manager import AlertManager
from models.gta_parameters import GTAParameters, StatusEnum
from models.alert import SeverityLevel, AlertType, AlertSource
from core.config import NOMINAL, THRESHOLDS


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_params(**overrides) -> GTAParameters:
    """Crée un GTAParameters nominal avec les overrides souhaités."""
    base = {
        "pressure_hp":    60.0,   "temperature_hp": 486.0,
        "steam_flow_hp":  120.0,  "pressure_bp":    4.5,
        "temperature_bp": 226.0,  "steam_flow_bp":  74.0,
        "turbine_speed":  6435.0, "active_power":   24.0,
        "power_factor":   0.85,   "valve_v1":       100.0,
        "valve_v2":       100.0,  "valve_v3":       100.0,
        "efficiency":     92.0,
    }
    base.update(overrides)
    return GTAParameters(**base)


@pytest.fixture
def am():
    """Retourne une instance fraîche d'AlertManager pour chaque test."""
    return AlertManager()


# ─────────────────────────────────────────────
# TESTS — PAS D'ALERTE EN NOMINAL
# ─────────────────────────────────────────────

class TestNoAlertInNominal:

    def test_nominal_no_alerts(self, am):
        alerts = am.check_thresholds(make_params())
        assert len(alerts) == 0

    def test_nominal_active_alerts_empty(self, am):
        am.check_thresholds(make_params())
        assert len(am.get_active_alerts()) == 0

    def test_small_noise_no_alert(self, am):
        """±0.5% de bruit ne doit pas déclencher d'alerte."""
        import random
        for _ in range(20):
            alerts = am.check_thresholds(make_params(
                pressure_hp    = 60.0 + random.gauss(0, 0.3),
                temperature_hp = 486.0 + random.gauss(0, 2.0),
            ))
            assert len(alerts) == 0


# ─────────────────────────────────────────────
# TESTS — DÉCLENCHEMENT DES ALERTES
# ─────────────────────────────────────────────

class TestAlertTriggering:

    def test_alert_low_pressure_hp(self, am):
        alerts = am.check_thresholds(make_params(pressure_hp=50.0))
        params = [a.parameter for a in alerts]
        assert "pressure_hp" in params

    def test_alert_high_temperature_hp(self, am):
        alerts = am.check_thresholds(make_params(temperature_hp=510.0))
        params = [a.parameter for a in alerts]
        assert "temperature_hp" in params

    def test_alert_high_pressure_hp(self, am):
        alerts = am.check_thresholds(make_params(pressure_hp=70.0))
        params = [a.parameter for a in alerts]
        assert "pressure_hp" in params

    def test_alert_low_power_factor(self, am):
        alerts = am.check_thresholds(make_params(power_factor=0.75))
        params = [a.parameter for a in alerts]
        assert "power_factor" in params

    def test_alert_low_turbine_speed(self, am):
        alerts = am.check_thresholds(make_params(turbine_speed=6000.0))
        params = [a.parameter for a in alerts]
        assert "turbine_speed" in params

    def test_multiple_alerts_on_multiple_violations(self, am):
        alerts = am.check_thresholds(make_params(
            pressure_hp    = 40.0,
            temperature_hp = 520.0,
            turbine_speed  = 5000.0,
        ))
        assert len(alerts) >= 3

    def test_alert_has_correct_parameter(self, am):
        alerts = am.check_thresholds(make_params(pressure_hp=40.0))
        pressure_alerts = [a for a in alerts if a.parameter == "pressure_hp"]
        assert len(pressure_alerts) >= 1

    def test_alert_value_matches_input(self, am):
        alerts = am.check_thresholds(make_params(pressure_hp=40.0))
        p_alert = next((a for a in alerts if a.parameter == "pressure_hp"), None)
        assert p_alert is not None
        assert abs(p_alert.value - 40.0) < 0.01

    def test_alert_threshold_is_limit_value(self, am):
        alerts = am.check_thresholds(make_params(pressure_hp=40.0))
        p_alert = next((a for a in alerts if a.parameter == "pressure_hp"), None)
        assert p_alert.threshold == THRESHOLDS["pressure_hp"]["min"]


# ─────────────────────────────────────────────
# TESTS — SÉVÉRITÉ
# ─────────────────────────────────────────────

class TestAlertSeverity:

    def test_small_violation_is_info_or_warning(self, am):
        """Déviation de ~3% → INFO ou WARNING."""
        alerts = am.check_thresholds(make_params(pressure_hp=53.5))  # -2.7% du seuil
        if alerts:
            assert alerts[0].severity in (
                SeverityLevel.INFO.value,
                SeverityLevel.WARNING.value
            )

    def test_large_violation_is_critical(self, am):
        """Déviation de -33% du seuil → CRITICAL."""
        alerts = am.check_thresholds(make_params(pressure_hp=30.0))
        critical = [a for a in alerts if a.severity == SeverityLevel.CRITICAL.value]
        assert len(critical) >= 1

    def test_medium_violation_is_warning(self, am):
        """Déviation de ~7% → WARNING."""
        alerts = am.check_thresholds(make_params(pressure_hp=51.0))
        if alerts:
            assert alerts[0].severity in (
                SeverityLevel.WARNING.value,
                SeverityLevel.CRITICAL.value
            )

    def test_severity_values_valid(self, am):
        valid = {s.value for s in SeverityLevel}
        alerts = am.check_thresholds(make_params(pressure_hp=40.0))
        for a in alerts:
            assert a.severity in valid


# ─────────────────────────────────────────────
# TESTS — ALERTES IA
# ─────────────────────────────────────────────

class TestAIAlerts:

    def test_add_ai_alert_returns_alert(self, am):
        alert = am.add_ai_alert("reconstruction_error", 0.08, 0.05)
        assert alert is not None
        assert alert.source == AlertSource.AI.value

    def test_ai_alert_type_is_anomaly(self, am):
        alert = am.add_ai_alert("reconstruction_error", 0.08, 0.05)
        assert alert.alert_type == AlertType.ANOMALY_DETECTED.value

    def test_ai_alert_in_active_list(self, am):
        am.add_ai_alert("active_power", 5.0, 10.0, "Chute de puissance détectée")
        actives = am.get_active_alerts()
        ai_alerts = [a for a in actives if a.source == AlertSource.AI.value]
        assert len(ai_alerts) >= 1

    def test_ai_alert_custom_message(self, am):
        msg   = "Test message anomalie"
        alert = am.add_ai_alert("turbine_speed", 5000.0, 6300.0, msg)
        assert alert.message == msg


# ─────────────────────────────────────────────
# TESTS — MISE À JOUR DES SEUILS
# ─────────────────────────────────────────────

class TestThresholdUpdate:

    def test_update_relaxes_threshold(self, am):
        """Élargir le seuil doit supprimer les alertes pour cette valeur."""
        am.update_thresholds({"pressure_hp": {"min": 30.0, "max": 80.0}})
        alerts = am.check_thresholds(make_params(pressure_hp=45.0))
        pressure_alerts = [a for a in alerts if a.parameter == "pressure_hp"]
        assert len(pressure_alerts) == 0

    def test_update_tightens_threshold(self, am):
        """Réduire le seuil doit déclencher des alertes sur des valeurs nominales."""
        am.update_thresholds({"pressure_hp": {"min": 65.0, "max": 70.0}})
        alerts = am.check_thresholds(make_params(pressure_hp=60.0))
        pressure_alerts = [a for a in alerts if a.parameter == "pressure_hp"]
        assert len(pressure_alerts) >= 1

    def test_get_thresholds_returns_dict(self, am):
        thresholds = am.get_thresholds()
        assert isinstance(thresholds, dict)
        assert "pressure_hp" in thresholds

    def test_get_thresholds_has_min_max(self, am):
        thresholds = am.get_thresholds()
        for param, limits in thresholds.items():
            assert "min" in limits
            assert "max" in limits

    def test_update_partial_preserves_other_thresholds(self, am):
        original_temp = am.get_thresholds()["temperature_hp"].copy()
        am.update_thresholds({"pressure_hp": {"min": 40.0, "max": 75.0}})
        assert am.get_thresholds()["temperature_hp"] == original_temp


# ─────────────────────────────────────────────
# TESTS — CLEAR ET GESTION MÉMOIRE
# ─────────────────────────────────────────────

class TestAlertManagement:

    def test_clear_empties_active_alerts(self, am):
        am.check_thresholds(make_params(pressure_hp=40.0))
        am.clear_alerts()
        assert len(am.get_active_alerts()) == 0

    def test_active_alerts_capped_at_200(self, am):
        """La mémoire des alertes est bornée à 200 entrées."""
        for _ in range(300):
            am.check_thresholds(make_params(pressure_hp=40.0))
        assert len(am.get_active_alerts()) <= 200

    def test_alert_has_timestamp(self, am):
        alerts = am.check_thresholds(make_params(pressure_hp=40.0))
        assert isinstance(alerts[0].timestamp, datetime)

    def test_alert_source_is_threshold(self, am):
        alerts = am.check_thresholds(make_params(pressure_hp=40.0))
        assert alerts[0].source == AlertSource.THRESHOLD.value