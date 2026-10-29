"""Adsorption chiller: characteristic map, driving-temperature range, limits and closure."""

import pytest

from gemini.core.modules.balance import energy_balance, mass_balance
from gemini.core.modules.heat import AdsorptionChiller
from gemini.core.types.flows import Stream
from gemini.errors import ConfigurationError, PhysicsRangeError

CP = 4217.4
GENERATOR = Stream(m_dot=5, T=343.15, p=3e5)
CHILLED = Stream(m_dot=5, T=291.15, p=3e5)
COOLING = Stream(m_dot=10, T=300.15, p=3e5)


def chiller(**params):
    """Return an adsorption chiller with a 2 kW/K characteristic and a 5 K threshold."""
    design = dict(
        capacity=1e5,
        characteristic_slope=2000,
        minimum_driving_difference=5,
        rejection_coefficient=2.0,
        evaporator_coefficient=1.0,
        auxiliary_power_ratio=0.02,
    )
    return AdsorptionChiller().update_params(**(design | params))


def call(machine, setpoint, **streams):
    """Call the chiller with the default circuits, replaced by ``streams``."""
    ports = dict(generator_in=GENERATOR, chilled_in=CHILLED, cooling_in=COOLING) | streams
    return machine(**ports, temperature_setpoint=setpoint)


def test_characteristic_hand_value_and_closure():
    """At 70/27/18 degC the duty follows the closed-form characteristic equation, COP 0.55."""
    machine = chiller()
    result = call(machine, 273.15 + 5)
    out = result.outputs
    ratio = 1 + 1 / 0.55 + 0.02
    sensitivity = (1 / 0.55) / (2 * 5 * CP) + 2.0 * ratio / (2 * 10 * CP) + 1.0 / (2 * 5 * CP)
    expected = 2000 * (70 - 2 * 27 + 18 - 5) / (1 + 2000 * sensitivity)
    assert out.evaporator_duty == pytest.approx(expected)
    assert out.evaporator_duty == pytest.approx(2000 * (out.driving_temperature_difference - 5))
    assert out.cop == pytest.approx(0.55) and out.is_capped
    assert out.generator_duty == pytest.approx(expected / 0.55)
    assert out.adsorber_condenser_duty == pytest.approx(expected * ratio)
    assert out.generator_out_T == pytest.approx(GENERATOR.T - expected / 0.55 / (5 * CP))
    assert energy_balance(machine, result)["relative_residual"] < 1e-12
    assert mass_balance(machine, result)["residual"] == 0


def test_setpoint_and_capacity():
    """A reachable setpoint is met; the capacity caps the evaporator duty."""
    out = call(chiller(), 273.15 + 17).outputs
    assert out.chilled_out_T == pytest.approx(273.15 + 17) and not out.is_capped
    capped = call(chiller(capacity=1e4), 273.15 + 15).outputs
    assert capped.evaporator_duty == 1e4 and capped.is_capped


def test_driving_temperature_range():
    """Below 55 degC the chiller is off; above 90 degC the map is out of range."""
    result = call(chiller(), 280, generator_in=GENERATOR.with_(T=273.15 + 50))
    assert result.outputs.evaporator_duty == 0 and result.outputs.cop is None
    assert result.outlets.chilled_out.T == CHILLED.T
    with pytest.raises(PhysicsRangeError, match="generator_in.T = 368.15"):
        call(chiller(), 280, generator_in=GENERATOR.with_(T=368.15))
    with pytest.raises(ConfigurationError, match="minimum_driving_temperature"):
        call(chiller(minimum_driving_temperature=370), 280)


def test_zero_and_negative_flow():
    """A stopped circuit gives no cold; a reversed flow raises."""
    out = call(chiller(), 280, cooling_in=COOLING.with_(m_dot=0)).outputs
    assert out.evaporator_duty == 0 and out.electricity == 0
    with pytest.raises(PhysicsRangeError, match="generator_in.m_dot = -2"):
        call(chiller(), 280, generator_in=GENERATOR.with_(m_dot=-2))
