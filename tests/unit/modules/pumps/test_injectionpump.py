"""Mass conservation for InjectionPump."""

import pytest

from gemini.errors import PhysicsError
from gemini.modules.pumps import InjectionPump
from gemini.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = InjectionPump().update_params(stage_count=10, pump_type="DEFAULT-PUMP")
    result = c(fluid_in=Stream(m_dot=1, T=300, p=1e6), pressure_setpoint=2e6)
    assert sum(s.m_dot for s in result.outlets.values() if isinstance(s, Stream)) == 1
    assert result.outlets["fluid_out"].T == 300
    assert result.outlets["fluid_out"].p >= 0


def _rows():
    return [
        dict(fluid_in=Stream(m_dot=m_dot, T=300, p=p), pressure_setpoint=setpoint, frequency=60)
        for m_dot, p, setpoint in [(1, 1e6, 2e6), (5, 2e6, 6e6), (0.5, 1e6, 1e6)]
    ]


def test_setpoint_matches_traced():
    """The setpoint branch traces and equals one call per row."""
    module = InjectionPump().update_params(efficiency=0.65)
    assert_module_matches(module, _rows())


def test_curves_match_traced():
    """The head and power curve branch traces and equals one call per row."""
    module = InjectionPump().update_params(
        stage_count=10,
        head_coefficients=[100, -0.01, 0, 0, 0, 0],
        power_coefficients=[1, 0.001, 0, 0, 0, 0],
    )
    rows = [{k: v for k, v in row.items() if k != "pressure_setpoint"} for row in _rows()]
    assert_module_matches(module, rows)


def test_setpoint_below_suction_raises():
    """A setpoint below the suction pressure is a physics range error."""
    with pytest.raises(PhysicsError, match="below suction pressure"):
        InjectionPump()(fluid_in=Stream(m_dot=1, T=300, p=2e6), pressure_setpoint=1e6)
