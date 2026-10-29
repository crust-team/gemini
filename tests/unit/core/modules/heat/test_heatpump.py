"""Heat pump and electric chiller duties, Carnot-fraction COP and limits."""

import pytest

from gemini.core.modules.balance import energy_balance, mass_balance
from gemini.core.modules.heat import HeatPump
from gemini.core.types.flows import Stream
from gemini.errors import PhysicsRangeError

CP = 4217.4


def heat_pump(mode, **params):
    """Return a configured heat pump."""
    return HeatPump().update_params(**({"mode": mode, "capacity": 2e6} | params))


def test_heating_hand_value_and_closure():
    """Sink at setpoint; the closed-form source outlet gives COP = 0.5 * 340 / 47.2 = 3.6."""
    pump = heat_pump("heating")
    source, sink = Stream(m_dot=20, T=300, p=3e5), Stream(m_dot=10, T=320, p=3e5)
    result = pump(source_in=source, sink_in=sink, temperature_setpoint=340)
    out = result.outputs
    assert out.useful_duty == out.condenser_duty == pytest.approx(10 * CP * 20)
    assert out.sink_out_T == 340
    assert out.source_out_T == pytest.approx(310 / (1 + 10 / 170))
    assert out.cop == pytest.approx(3.6)
    assert out.cop == pytest.approx(0.5 * 340 / (340 - out.source_out_T))
    assert out.electricity == pytest.approx(out.useful_duty / 3.6)
    assert out.evaporator_duty == pytest.approx(20 * CP * (300 - out.source_out_T))
    assert out.temperature_lift == pytest.approx(340 - out.source_out_T)
    assert out.is_running and not out.is_capped
    assert result.outlets.sink_out.p == sink.p and result.outlets.source_out.m_dot == 20
    assert energy_balance(pump, result)["relative_residual"] < 1e-12
    assert mass_balance(pump, result)["residual"] == 0


def test_cooling_mode_is_an_electric_chiller():
    """Chilled outlet at setpoint; condenser takes evaporator duty plus electricity."""
    chiller = heat_pump("cooling")
    source, sink = Stream(m_dot=20, T=285, p=3e5), Stream(m_dot=30, T=300, p=3e5)
    result = chiller(source_in=source, sink_in=sink, temperature_setpoint=280)
    out = result.outputs
    load = 20 * CP * 5 / (30 * CP)
    assert out.useful_duty == out.evaporator_duty == pytest.approx(20 * CP * 5)
    assert out.source_out_T == 280
    assert out.sink_out_T == pytest.approx((300 - load) / (1 - load / 140))
    assert out.cop == pytest.approx(0.5 * 280 / (out.sink_out_T - 280))
    assert out.condenser_duty == pytest.approx(out.evaporator_duty * (1 + 1 / out.cop))
    assert energy_balance(chiller, result)["relative_residual"] < 1e-12
    assert mass_balance(chiller, result)["residual"] == 0


def test_capacity_cap_and_lift_floor():
    """The useful duty stops at capacity; a small lift uses the floor in the COP."""
    pump = heat_pump("heating", capacity=5e5)
    source, sink = Stream(m_dot=20, T=300, p=3e5), Stream(m_dot=10, T=320, p=3e5)
    out = pump(source_in=source, sink_in=sink, temperature_setpoint=340).outputs
    assert out.is_capped and out.useful_duty == 5e5
    assert out.sink_out_T == pytest.approx(320 + 5e5 / (10 * CP)) and out.sink_out_T < 340
    warm = Stream(m_dot=40, T=330, p=3e5)
    result = pump(source_in=warm, sink_in=sink, temperature_setpoint=330)
    out = result.outputs
    assert out.temperature_lift < 10
    assert out.cop == pytest.approx(0.5 * 330 / 10)
    assert energy_balance(pump, result)["relative_residual"] < 1e-12
    cooled = heat_pump("cooling")(
        source_in=Stream(m_dot=20, T=300, p=3e5),
        sink_in=Stream(m_dot=200, T=290, p=3e5),
        temperature_setpoint=295,
    ).outputs
    assert cooled.cop == pytest.approx(0.5 * 295 / 10)


def test_machine_off_without_demand_flow_or_part_load():
    """No request, a stopped circuit or a load below the minimum leaves both streams as they are."""
    pump = heat_pump("heating", minimum_part_load=0.3)
    source, sink = Stream(m_dot=20, T=300, p=3e5), Stream(m_dot=10, T=320, p=3e5)
    cases = [
        dict(source_in=source, sink_in=sink, temperature_setpoint=310),
        dict(source_in=source.with_(m_dot=0), sink_in=sink, temperature_setpoint=340),
        dict(source_in=source, sink_in=sink.with_(m_dot=0), temperature_setpoint=340),
        dict(source_in=source, sink_in=sink, temperature_setpoint=321),
    ]
    for case in cases:
        result = pump(**case)
        out = result.outputs
        assert out.cop is None and not out.is_running and not out.is_capped
        assert out.useful_duty == out.electricity == out.evaporator_duty == 0
        assert result.outlets.source_out.T == case["source_in"].T
        assert result.outlets.sink_out.T == case["sink_in"].T


def test_invalid_operating_points_raise():
    """Negative flow, a hopeless heating lift and a too small sink flow are out of range."""
    source, sink = Stream(m_dot=20, T=300, p=3e5), Stream(m_dot=10, T=320, p=3e5)
    with pytest.raises(PhysicsRangeError, match="source_in.m_dot = -1"):
        heat_pump("heating")(
            source_in=source.with_(m_dot=-1), sink_in=sink, temperature_setpoint=340
        )
    with pytest.raises(PhysicsRangeError, match="heating COP above 1"):
        heat_pump("heating", carnot_efficiency=0.2)(
            source_in=source.with_(T=270), sink_in=sink, temperature_setpoint=340
        )
    with pytest.raises(PhysicsRangeError, match="to reject the cooling duty"):
        heat_pump("cooling")(
            source_in=Stream(m_dot=100, T=290, p=3e5),
            sink_in=Stream(m_dot=0.1, T=300, p=3e5),
            temperature_setpoint=280,
        )
