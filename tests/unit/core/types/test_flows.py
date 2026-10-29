"""Stream construction from public units, validation and copies."""

import pytest
from pydantic import ValidationError

from gemini.core import runtime
from gemini.core.physics.units import Quantity
from gemini.core.types.flows import Stream
from gemini.core.types.fluid import BRINE, WATER, Fluid
from gemini.errors import UnitError


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
