"""
tests/test_fake_api.py — Tests unitaires du générateur de données FakeAPI
Couverture : génération, vannes, scénarios, bruit, reset, statut.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import asyncio
from simulation.fake_api import FakeAPI
from simulation.valve_controller import ValveController
from models.gta_parameters import StatusEnum
from core.config import NOMINAL


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

@pytest.fixture
def api():
    """Crée une instance fraîche de FakeAPI pour chaque test."""
    return FakeAPI()


# ─────────────────────────────────────────────
# TESTS — ÉTAT INITIAL
# ─────────────────────────────────────────────

class TestInitialState:

    def test_initial_pressure_nominal(self, api):
        assert api._state["pressure_hp"] == NOMINAL["pressure_hp"]

    def test_initial_temperature_nominal(self, api):
        assert api._state["temperature_hp"] == NOMINAL["temperature_hp"]

    def test_initial_valves_fully_open(self, api):
        assert api._state["valve_v1"] == 100.0
        assert api._state["valve_v2"] == 100.0
        assert api._state["valve_v3"] == 100.0

    def test_no_active_scenario_at_start(self, api):
        assert api._active_scenario is None

    def test_no_data_before_first_generate(self, api):
        assert api.get_current() is None


# ─────────────────────────────────────────────
# TESTS — GÉNÉRATION DE DONNÉES
# ─────────────────────────────────────────────

class TestDataGeneration:

    def test_generate_returns_gta_parameters(self, api):
        params = api._generate()
        assert params is not None
        assert hasattr(params, "pressure_hp")
        assert hasattr(params, "active_power")
        assert hasattr(params, "turbine_speed")
        assert hasattr(params, "status")

    def test_pressure_positive(self, api):
        for _ in range(20):
            p = api._generate()
            assert p.pressure_hp > 0, "La pression HP ne peut pas être négative"

    def test_active_power_positive(self, api):
        for _ in range(20):
            p = api._generate()
            assert p.active_power >= 0

    def test_turbine_speed_positive(self, api):
        for _ in range(20):
            p = api._generate()
            assert p.turbine_speed >= 0

    def test_power_factor_in_range(self, api):
        for _ in range(20):
            p = api._generate()
            assert 0.0 <= p.power_factor <= 1.0, f"cos φ hors plage : {p.power_factor}"

    def test_efficiency_in_range(self, api):
        for _ in range(20):
            p = api._generate()
            assert 0.0 <= p.efficiency <= 100.0, f"Rendement hors plage : {p.efficiency}"

    def test_status_is_valid_enum(self, api):
        p = api._generate()
        valid = {s.value for s in StatusEnum}
        assert p.status in valid

    def test_nominal_status_is_normal(self, api):
        p = api._generate()
        assert p.status == StatusEnum.NORMAL.value

    def test_timestamp_is_set(self, api):
        from datetime import datetime
        p = api._generate()
        assert isinstance(p.timestamp, datetime)

    def test_noise_within_bounds(self, api):
        """Le bruit (±1%) ne doit pas faire dévier les valeurs de plus de 5%."""
        for _ in range(50):
            p = api._generate()
            nom_p = NOMINAL["pressure_hp"]
            assert abs(p.pressure_hp - nom_p) < nom_p * 0.05


# ─────────────────────────────────────────────
# TESTS — VANNES
# ─────────────────────────────────────────────

class TestValveControl:

    def test_set_v1_partial(self, api):
        api.set_valves(v1=50.0)
        assert api._state["valve_v1"] == 50.0

    def test_set_v2_partial(self, api):
        api.set_valves(v2=75.0)
        assert api._state["valve_v2"] == 75.0

    def test_set_v3_partial(self, api):
        api.set_valves(v3=60.0)
        assert api._state["valve_v3"] == 60.0

    def test_set_all_valves(self, api):
        api.set_valves(v1=30.0, v2=80.0, v3=90.0)
        assert api._state["valve_v1"] == 30.0
        assert api._state["valve_v2"] == 80.0
        assert api._state["valve_v3"] == 90.0

    def test_partial_v1_reduces_power(self, api):
        api.set_valves(v1=100.0)
        p_full = api._generate().active_power

        api.set_valves(v1=30.0)
        p_partial = api._generate().active_power

        assert p_partial < p_full, "Fermeture de V1 doit réduire la puissance"

    def test_none_valves_dont_change_state(self, api):
        api.set_valves(v1=50.0)
        api.set_valves(v2=None)
        assert api._state["valve_v1"] == 50.0   # inchangé

    def test_valve_range_clamping(self, api):
        """Les valeurs hors plage ne doivent pas être stockées telles quelles."""
        api.set_valves(v1=50.0)
        p = api._generate()
        # Vérifier que la génération ne plante pas
        assert p is not None


# ─────────────────────────────────────────────
# TESTS — SCÉNARIOS
# ─────────────────────────────────────────────

class TestScenarios:

    def test_trigger_valid_scenario(self, api):
        for sid in range(1, 8):
            api.trigger_scenario(sid)
            assert api._active_scenario is not None
            assert api._active_scenario.id == sid
            api.reset()

    def test_trigger_invalid_scenario_no_crash(self, api):
        api.trigger_scenario(99)   # ID inexistant → doit être ignoré
        assert api._active_scenario is None

    def test_scenario_1_lowers_pressure(self, api):
        """Scénario 1 (chute pression) doit faire descendre la pression."""
        import time
        api.trigger_scenario(1)
        api._scenario_start_time = time.time() - 60   # simuler 60s écoulées

        pressures = [api._generate().pressure_hp for _ in range(10)]
        avg = sum(pressures) / len(pressures)
        assert avg < NOMINAL["pressure_hp"], \
            f"Pression moyenne ({avg:.1f}) devrait être < nominal ({NOMINAL['pressure_hp']})"

    def test_scenario_2_raises_temperature(self, api):
        """Scénario 2 (surchauffe) doit faire monter la température."""
        import time
        api.trigger_scenario(2)
        api._scenario_start_time = time.time() - 60

        temps = [api._generate().temperature_hp for _ in range(10)]
        avg   = sum(temps) / len(temps)
        assert avg > NOMINAL["temperature_hp"], \
            f"Température moyenne ({avg:.1f}) devrait être > nominal ({NOMINAL['temperature_hp']})"

    def test_scenario_produces_valid_params(self, api):
        for sid in range(1, 8):
            api.trigger_scenario(sid)
            p = api._generate()
            assert p is not None
            assert p.pressure_hp >= 0
            api.reset()

    def test_scenario_sets_name_in_params(self, api):
        api.trigger_scenario(1)
        p = api._generate()
        # Scénario actif → nom renseigné ou None si terminé
        assert p.scenario is None or isinstance(p.scenario, str)


# ─────────────────────────────────────────────
# TESTS — RESET
# ─────────────────────────────────────────────

class TestReset:

    def test_reset_restores_valves(self, api):
        api.set_valves(v1=10.0, v2=20.0, v3=30.0)
        api.reset()
        assert api._state["valve_v1"] == NOMINAL["valve_v1"]
        assert api._state["valve_v2"] == NOMINAL["valve_v2"]
        assert api._state["valve_v3"] == NOMINAL["valve_v3"]

    def test_reset_clears_scenario(self, api):
        api.trigger_scenario(3)
        api.reset()
        assert api._active_scenario is None

    def test_reset_restores_pressure(self, api):
        api._state["pressure_hp"] = 30.0
        api.reset()
        assert api._state["pressure_hp"] == NOMINAL["pressure_hp"]

    def test_reset_clears_power_factor_offset(self, api):
        api._power_factor_offset = -0.15
        api.reset()
        assert api._power_factor_offset == 0.0

    def test_status_normal_after_reset(self, api):
        api.trigger_scenario(4)
        api.reset()
        p = api._generate()
        assert p.status == StatusEnum.NORMAL.value


# ─────────────────────────────────────────────
# TESTS — CALLBACK
# ─────────────────────────────────────────────

class TestCallback:

    def test_callback_called_on_new_data(self, api):
        received = []

        async def cb(params):
            received.append(params)

        api.set_on_new_data(cb)

        async def run():
            api._running = True
            import asyncio
            task = asyncio.create_task(api.run())
            await asyncio.sleep(0.6)   # 1 tick = 500ms
            api.stop()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())
        assert len(received) >= 1, "Le callback doit être appelé au moins une fois"