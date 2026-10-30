"""Stream construction from public units, validation and copies."""

import numpy as np
import pytest
from pydantic import ValidationError

from gemini.core import runtime
from gemini.core.physics.units import Quantity
from gemini.core.types.flows import Stream, StreamState
from gemini.core.types.fluid import BRINE, WATER, Fluid
from gemini.errors import PhysicsRangeError, UnitError


def test_mass_flow_inputs_and_units():
    """Plain numbers are kg/s; unit strings and quantities convert to SI fields."""
    assert Stream(flow=2, T=300, p=1e5).m_dot == 2
    stream = Stream(flow="36 t/h", T="25 degC", p="2 bar")
    assert (stream.m_dot, stream.T, stream.p) == (10, 298.15, 2e5)
    assert Stream(m_dot=Quantity(3.6, "t/h"), T=300, p=1e5).m_dot == pytest.approx(1)


def test_volume_flow_uses_the_stream_fluid_density():
    """Volume flow units convert to mass flow with the selected fluid."""
    fluid = Fluid(liquid_density=1068)
    stream = Stream(flow="360 m3/h", T=300, p=1e5, fluid=fluid)
    assert stream.m_dot == pytest.approx(106.8)
    assert stream.volumetric_flow() == pytest.approx(0.1)
    assert Stream(flow=Quantity(1, "l/s"), T=300, p=1e5).m_dot == pytest.approx(1)


def test_flow_text_without_a_unit_is_a_unit_error():
    """Flow text must carry a unit; formerly this raised IndexError."""
    for text in ("10", "abc", "  "):
        with pytest.raises(UnitError, match="Stream.flow"):
            Stream(flow=text, T=300, p=1e5)


def test_flow_and_mass_flow_together_are_rejected():
    """Supplying both flow and m_dot is ambiguous; formerly m_dot was silently dropped."""
    with pytest.raises(TypeError, match="either flow or m_dot"):
        Stream(flow=1, m_dot=2, T=300, p=1e5)


def test_default_fluid_and_physical_limits():
    """The runtime default fluid fills a missing fluid; absolute T and p stay physical."""
    assert Stream(m_dot=1, T=300, p=1e5).fluid == BRINE
    with runtime.settings(default_fluid=WATER):
        assert Stream(m_dot=1, T=300, p=1e5).fluid == WATER
    with pytest.raises(ValidationError):
        Stream(m_dot=1, T=0, p=1e5)
    with pytest.raises(ValidationError):
        Stream(m_dot=1, T=300, p=-1)


def test_with_revalidates_the_copy():
    """Copies keep the fluid and revalidate changed fields."""
    stream = Stream(m_dot=-1, T=300, p=1e5, fluid=WATER)
    assert stream.with_(p=2e5) == Stream(m_dot=-1, T=300, p=2e5, fluid=WATER)
    with pytest.raises(ValidationError):
        stream.with_(T=-1)


def test_stream_state_carries_array_values_and_keeps_the_physical_limits():
    """A state over time computes volume flow from its density; copies keep p >= 0, T > 0."""
    properties = {"rho_l": 1068.0, "rho_g": 1.976, "gmf": 0.0}
    state = StreamState.from_fluid(
        m_dot=np.array([10.68, 21.36]),
        T=np.array([300.0, 310.0]),
        p=1e5,
        fluid=BRINE,
        properties=properties,
    )
    assert state.volumetric_flow().tolist() == pytest.approx([0.01, 0.02], rel=1e-15)
    assert state.with_(p=np.array([2e5, 3e5])).p.tolist() == [2e5, 3e5]
    with pytest.raises(PhysicsRangeError, match="p = -1.0 Pa"):
        state.with_(p=np.array([1e5, -1.0]))
    with pytest.raises(PhysicsRangeError, match="T = 0.0 K"):
        state.with_(T=0.0)
