"""Gas compressor: ideal-gas stages, intercooling, gas-enthalpy closure and limits."""

import pytest

from gemini.errors import PhysicsError
from gemini.modules.balance import energy_balance, mass_balance
from gemini.modules.pumps import GasCompressor
from gemini.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches

GAS = Stream(m_dot=0.2, T=300, p=1e5)


def compressor(**changes):
    """Return an air-like machine: k = 1.4, cp = 1005 J/kg/K and a 0.95 motor."""
    params = dict(
        isentropic_efficiency=0.8,
        heat_capacity_ratio=1.4,
        gas_specific_heat=1005,
        motor_efficiency=0.95,
    )
    return GasCompressor().update_params(**params | changes)


def test_single_stage_by_hand():
    """One stage from 1 to 8 bar follows T_2s = T_1 r^((k-1)/k) and T_2 = T_1 + dT_s / eta."""
    result = compressor()(suction=GAS, pressure_setpoint=8e5)
    out = result.outputs
    ideal = 300 * 8 ** (0.4 / 1.4)
    outlet_T = 300 + (ideal - 300) / 0.8
    assert out.pressure_ratio == 8
    assert out.discharge_T == pytest.approx(outlet_T)
    assert out.shaft_power == pytest.approx(0.2 * 1005 * (outlet_T - 300))
    assert out.electricity == pytest.approx(out.shaft_power / 0.95)
    assert out.heat_loss == pytest.approx(out.electricity - out.shaft_power)
    discharge = result.outlets.discharge
    assert discharge.p == 8e5 and discharge.T == out.discharge_T and discharge.m_dot == 0.2
    assert discharge.fluid == GAS.fluid


def test_intercooled_stages_save_work_and_close_in_gas_enthalpy():
    """Two intercooled stages need less work; electricity = m cp (T_2 - T_1) + heat_loss."""
    single = compressor()(suction=GAS, pressure_setpoint=16e5).outputs
    machine = compressor(stage_count=2)
    result = machine(suction=GAS, pressure_setpoint=16e5)
    out = result.outputs
    assert out.shaft_power < single.shaft_power
    assert out.discharge_T == pytest.approx(300 + 300 * (4 ** (0.4 / 1.4) - 1) / 0.8)
    gas_heating = 0.2 * 1005 * (out.discharge_T - 300)
    assert out.shaft_power == pytest.approx(2 * gas_heating)
    assert out.electricity == pytest.approx(gas_heating + out.heat_loss, rel=1e-12)
    assert mass_balance(machine, result)["residual"] == 0


def test_sensible_audit_differs_by_the_liquid_heat_capacity():
    """The stream audit values the gas with cp_l, so its residual is m dT (cp - cp_l)."""
    machine = compressor()
    result = machine(suction=GAS, pressure_setpoint=4e5)
    rise = result.outputs.discharge_T - 300
    expected = 0.2 * rise * (1005 - 4217.4)
    assert energy_balance(machine, result)["residual"] == pytest.approx(expected, rel=1e-9)


def test_zero_flow_unit_ratio_and_invalid_setpoints():
    """No flow or no lift draws no power; expansion and reverse flow raise."""
    out = compressor()(suction=GAS.with_(m_dot=0), pressure_setpoint=8e5).outputs
    assert out.shaft_power == 0 and out.electricity == 0 and out.heat_loss == 0
    assert out.discharge_T > 300
    out = compressor()(suction=GAS, pressure_setpoint=1e5).outputs
    assert out.pressure_ratio == 1 and out.shaft_power == 0 and out.discharge_T == 300
    with pytest.raises(PhysicsError, match="pressure_setpoint = 50000"):
        compressor()(suction=GAS, pressure_setpoint=5e4)
    with pytest.raises(PhysicsError, match="reverse flow"):
        compressor()(suction=GAS.with_(m_dot=-0.1), pressure_setpoint=8e5)


def test_traced_call_matches_one_call_per_row():
    """Single and intercooled stages at several ratios trace and equal one call per row."""
    rows = [
        dict(suction=Stream(m_dot=m_dot, T=300.0, p=p), pressure_setpoint=setpoint)
        for m_dot, p, setpoint in [
            (0.2, 1e5, 4e5),
            (0.0, 1e5, 4e5),
            (0.5, 1e5, 1e5),
            (0.1, 2e5, 3e6),
        ]
    ]
    assert_module_matches(compressor(), rows)
    assert_module_matches(compressor(stage_count=3), rows)
