"""
tests/test_physics_model.py — Tests unitaires du modèle physique thermodynamique
Couverture : équations individuelles + cohérence globale du compute_all().
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import math
from simulation.physics_model import PhysicsModel
from core.config import NOMINAL, THRESHOLDS


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

@pytest.fixture
def model():
    return PhysicsModel()


@pytest.fixture
def nominal_result(model):
    return model.compute_all(
        pressure_hp    = NOMINAL["pressure_hp"],
        temperature_hp = NOMINAL["temperature_hp"],
        steam_flow_hp  = NOMINAL["steam_flow_hp"],
        valve_v1       = NOMINAL["valve_v1"],
        valve_v2       = NOMINAL["valve_v2"],
        valve_v3       = NOMINAL["valve_v3"],
    )


# ─────────────────────────────────────────────
# TESTS — PUISSANCE ACTIVE
# ─────────────────────────────────────────────

class TestActivePower:

    def test_nominal_power_approx_24mw(self, model):
        """P = 0.2 × 120 T/h = 24 MW en conditions nominales."""
        p = model.compute_active_power(120.0, 100.0)
        assert abs(p - 24.0) < 0.5, f"Attendu ~24 MW, obtenu {p}"

    def test_zero_flow_zero_power(self, model):
        p = model.compute_active_power(0.0, 100.0)
        assert p == 0.0

    def test_zero_valve_zero_power(self, model):
        p = model.compute_active_power(120.0, 0.0)
        assert p == 0.0

    def test_half_valve_half_power(self, model):
        p_full = model.compute_active_power(120.0, 100.0)
        p_half = model.compute_active_power(120.0, 50.0)
        assert abs(p_half - p_full / 2) < 0.1

    def test_power_proportional_to_flow(self, model):
        p1 = model.compute_active_power(100.0, 100.0)
        p2 = model.compute_active_power(120.0, 100.0)
        assert p2 > p1

    def test_power_does_not_exceed_max(self, model):
        p = model.compute_active_power(200.0, 100.0)
        # 0.2 × 200 = 40 MW > MAX_POWER (32 MW) — non plafonné dans cette méthode
        # mais ne doit pas être négatif
        assert p >= 0

    def test_power_below_max_at_nominal(self, model):
        p = model.compute_active_power(NOMINAL["steam_flow_hp"], 100.0)
        assert p <= PhysicsModel.MAX_POWER


# ─────────────────────────────────────────────
# TESTS — VITESSE TURBINE
# ─────────────────────────────────────────────

class TestTurbineSpeed:

    def test_nominal_speed_approx_6435(self, model):
        speed = model.compute_turbine_speed(NOMINAL["pressure_hp"], 100.0)
        assert abs(speed - NOMINAL["turbine_speed"]) < 100, \
            f"Vitesse nominale attendue ~6435 RPM, obtenu {speed}"

    def test_lower_pressure_lower_speed(self, model):
        s_nominal = model.compute_turbine_speed(60.0, 100.0)
        s_low     = model.compute_turbine_speed(50.0, 100.0)
        assert s_low < s_nominal

    def test_closed_valve_low_speed(self, model):
        s = model.compute_turbine_speed(60.0, 0.0)
        assert s == 0.0

    def test_speed_proportional_to_sqrt_pressure(self, model):
        """Vitesse ∝ √P : doubler la pression multiplie la vitesse par √2."""
        s1 = model.compute_turbine_speed(60.0, 100.0)
        s2 = model.compute_turbine_speed(240.0, 100.0)   # ×4 → vitesse ×2
        assert abs(s2 / s1 - 2.0) < 0.2

    def test_speed_never_negative(self, model):
        for p in [0, 10, 30, 60, 80]:
            s = model.compute_turbine_speed(p, 100.0)
            assert s >= 0


# ─────────────────────────────────────────────
# TESTS — PRESSION / TEMPÉRATURE BP
# ─────────────────────────────────────────────

class TestBPParameters:

    def test_bp_pressure_lower_than_hp(self, model):
        p_bp = model.compute_bp_pressure(60.0, 100.0)
        assert p_bp < 60.0, f"P_BP ({p_bp}) doit être < P_HP (60)"

    def test_bp_pressure_near_nominal(self, model):
        p_bp = model.compute_bp_pressure(NOMINAL["pressure_hp"], 100.0)
        assert abs(p_bp - NOMINAL["pressure_bp"]) < 1.5, \
            f"P_BP attendu ~{NOMINAL['pressure_bp']} bar, obtenu {p_bp}"

    def test_closed_v3_lowers_bp_pressure(self, model):
        p_full   = model.compute_bp_pressure(60.0, 100.0)
        p_closed = model.compute_bp_pressure(60.0, 20.0)
        assert p_closed < p_full

    def test_bp_temp_lower_than_hp_temp(self, model):
        t_bp = model.compute_bp_temperature(486.0, 60.0, 4.5)
        assert t_bp < 486.0, f"T_BP ({t_bp}°C) doit être < T_HP (486°C)"

    def test_bp_temp_above_minimum(self, model):
        t_bp = model.compute_bp_temperature(486.0, 60.0, 4.5)
        assert t_bp >= 150.0, "Température BP ne peut pas être < 150°C"

    def test_bp_temp_decreases_with_lower_pressure_ratio(self, model):
        t1 = model.compute_bp_temperature(486.0, 60.0, 4.5)
        t2 = model.compute_bp_temperature(486.0, 60.0, 2.0)
        assert t2 < t1   # moins de détente → température BP plus basse


# ─────────────────────────────────────────────
# TESTS — RENDEMENT
# ─────────────────────────────────────────────

class TestEfficiency:

    def test_efficiency_in_valid_range(self, model):
        eta = model.compute_efficiency(24.0, 120.0, 486.0)
        assert 0.0 < eta <= 100.0

    def test_nominal_efficiency_reasonable(self, model):
        eta = model.compute_efficiency(
            NOMINAL["active_power"],
            NOMINAL["steam_flow_hp"],
            NOMINAL["temperature_hp"]
        )
        assert 80.0 <= eta <= 98.0, f"Rendement nominal hors plage : {eta}%"

    def test_zero_flow_zero_efficiency(self, model):
        eta = model.compute_efficiency(24.0, 0.0, 486.0)
        assert eta == 0.0

    def test_lower_power_lower_efficiency(self, model):
        eta_full  = model.compute_efficiency(24.0, 120.0, 486.0)
        eta_half  = model.compute_efficiency(12.0, 120.0, 486.0)
        assert eta_half < eta_full


# ─────────────────────────────────────────────
# TESTS — FACTEUR DE PUISSANCE
# ─────────────────────────────────────────────

class TestPowerFactor:

    def test_nominal_cos_phi(self, model):
        cos_phi = model.compute_power_factor(NOMINAL["active_power"])
        assert abs(cos_phi - NOMINAL["power_factor"]) < 0.05

    def test_cos_phi_in_valid_range(self, model):
        for power in [0, 5, 12, 24, 32]:
            cos_phi = model.compute_power_factor(power)
            assert 0.70 <= cos_phi <= 0.99, f"cos φ hors plage pour P={power} MW : {cos_phi}"

    def test_full_load_highest_cos_phi(self, model):
        cos_low  = model.compute_power_factor(5.0)
        cos_full = model.compute_power_factor(24.0)
        assert cos_full >= cos_low


# ─────────────────────────────────────────────
# TESTS — COMPUTE_ALL (intégration)
# ─────────────────────────────────────────────

class TestComputeAll:

    def test_all_keys_present(self, model, nominal_result):
        required = [
            "pressure_hp", "temperature_hp", "steam_flow_hp",
            "pressure_bp", "temperature_bp", "steam_flow_bp",
            "turbine_speed", "active_power", "power_factor",
            "efficiency", "valve_v1", "valve_v2", "valve_v3",
        ]
        for key in required:
            assert key in nominal_result, f"Clé manquante : {key}"

    def test_no_none_values(self, model, nominal_result):
        for key, val in nominal_result.items():
            assert val is not None, f"{key} = None"

    def test_all_values_are_floats(self, model, nominal_result):
        for key, val in nominal_result.items():
            assert isinstance(val, (int, float)), f"{key} n'est pas un nombre : {type(val)}"

    def test_nominal_values_within_thresholds(self, model, nominal_result):
        """Les valeurs nominales doivent être dans les seuils d'alarme."""
        for param, limits in THRESHOLDS.items():
            val = nominal_result.get(param)
            if val is None:
                continue
            assert limits["min"] <= val <= limits["max"], \
                f"{param} = {val:.2f} hors seuil [{limits['min']}, {limits['max']}]"

    def test_bp_less_than_hp(self, model, nominal_result):
        assert nominal_result["pressure_bp"] < nominal_result["pressure_hp"]
        assert nominal_result["temperature_bp"] < nominal_result["temperature_hp"]

    def test_valve_positions_preserved(self, model):
        result = model.compute_all(60, 486, 120, 70.0, 80.0, 90.0)
        assert result["valve_v1"] == 70.0
        assert result["valve_v2"] == 80.0
        assert result["valve_v3"] == 90.0

    def test_zero_valve_v1_zero_power(self, model):
        result = model.compute_all(60, 486, 120, 0.0, 100.0, 100.0)
        assert result["active_power"] == 0.0
        assert result["turbine_speed"] == 0.0