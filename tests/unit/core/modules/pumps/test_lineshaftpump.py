"""Line-shaft pump: ESP polynomial basis, shaft friction and isothermal bookkeeping."""

import pytest

from gemini.core.modules.balance import energy_balance, mass_balance
from gemini.core.modules.pumps import ESP, LineShaftPump
from gemini.core.physics import units
from gemini.core.types.flows import Stream
from gemini.errors import PhysicsRangeError

CURVES = {
    "no_stages": 12,
    "head_coeff": [83.08389282, -0.000460444, -1.19e-07, 1.69e-11, -6.36e-16, 6.69e-21],
    "power_coeff": [10.02089977, -0.000160233, 6.52e-08, -2.13e-12, 1.71e-17, 1.38e-23],
}


def pump(**changes):
    """Return a 12-stage pump set at 300 m with 5 W/m of shaft friction at 60 Hz."""
    params = dict(CURVES, setting_depth=300, shaft_friction_loss=5, motor_efficiency=0.9)
    return LineShaftPump().update_params(**params | changes)


def test_pump_stages_match_the_esp_basis_and_friction_scales_with_speed():
    """Head and pump power equal the ESP curves; friction is loss * depth * f / 60 Hz."""
    suction = Stream(m_dot=units.m3h_to_m3s(200) * 1000, T=340, p=1e6)
    esp = ESP().update_params(**CURVES)(suction=suction, frequency=50).outputs
    result = pump()(suction=suction, frequency=50)
    out = result.outputs
    assert out.head == pytest.approx(esp.head)
    assert out.pump_power == pytest.approx(esp.power)
    assert out.shaft_friction_power == pytest.approx(5 * 300 * 50 / 60)
    assert out.shaft_power == pytest.approx(esp.power + 1250)
    assert out.electricity == pytest.approx((esp.power + 1250) / 0.9)
    assert out.efficiency == pytest.approx(out.flow * out.head / out.pump_power)
    assert result.outlets.discharge.T == 340
    assert result.outlets.discharge.p == pytest.approx(1e6 + esp.head)


def test_isothermal_electricity_is_unresolved_pump_power():
    """The audit reports all electricity as unresolved; the thermal part closes."""
    machine = pump()
    result = machine(suction=Stream(m_dot=40, T=340, p=1e6), frequency=55)
    balance = energy_balance(machine, result)
    assert balance["unresolved_power"] == result.outputs.electricity
    assert balance["relative_thermal_residual"] < 1e-12
    assert mass_balance(machine, result)["residual"] == 0


def test_zero_flow_runs_at_shutoff():
    """At zero flow the pump holds its shutoff head and draws the shutoff power."""
    out = pump(shaft_friction_loss=0)(suction=Stream(m_dot=0, T=340, p=1e6), frequency=60).outputs
    assert out.head == pytest.approx(units.ft_head_to_pa(12 * 83.08389282))
    assert out.pump_power == pytest.approx(units.bhp_to_w(12 * 10.02089977))
    assert out.efficiency == 0


def test_reverse_flow_and_off_curve_raise():
    """Reverse flow, a negative head and a negative pump power raise PhysicsRangeError."""
    suction = Stream(m_dot=40, T=340, p=1e6)
    with pytest.raises(PhysicsRangeError, match="reverse flow"):
        pump()(suction=suction.with_(m_dot=-1), frequency=50)
    with pytest.raises(PhysicsRangeError, match="head curve"):
        pump(head_coeff=[-1, 0, 0, 0, 0, 0])(suction=suction, frequency=50)
    with pytest.raises(PhysicsRangeError, match="power curve"):
        pump(power_coeff=[-1, 0, 0, 0, 0, 0])(suction=suction, frequency=50)
