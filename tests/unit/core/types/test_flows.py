"""Stream construction from public units, validation and copies."""

import copy
import json
import pickle
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from pydantic_core import to_jsonable_python

from gemini.core import runtime
from gemini.core.physics.units import Quantity
from gemini.core.types.flows import Stream
from gemini.core.types.fluid import BRINE, WATER, Fluid
from gemini.errors import CallError, PhysicsRangeError, UnitError


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
    with pytest.raises(PhysicsRangeError):
        Stream(m_dot=1, T=0, p=1e5)
    with pytest.raises(PhysicsRangeError):
        Stream(m_dot=1, T=300, p=-1)


def test_with_revalidates_the_copy():
    """Copies keep the fluid and revalidate changed fields."""
    stream = Stream(m_dot=-1, T=300, p=1e5, fluid=WATER)
    assert stream.with_(p=2e5) == Stream(m_dot=-1, T=300, p=2e5, fluid=WATER)
    with pytest.raises(PhysicsRangeError):
        stream.with_(T=-1)


def test_stream_carries_array_values_and_keeps_the_physical_limits():
    """A stream over time computes volume flow from its fluid; copies keep p >= 0, T > 0."""
    fluid = Fluid(liquid_density=1068)
    stream = Stream(m_dot=np.array([10.68, 21.36]), T=np.array([300.0, 310.0]), p=1e5, fluid=fluid)
    assert stream.volumetric_flow().tolist() == pytest.approx([0.01, 0.02], rel=1e-15)
    assert stream.with_(p=np.array([2e5, 3e5])).p.tolist() == [2e5, 3e5]
    with pytest.raises(PhysicsRangeError, match="p = -1.0 Pa"):
        stream.with_(p=np.array([1e5, -1.0]))
    with pytest.raises(PhysicsRangeError, match="T = 0.0 K"):
        stream.with_(T=0.0)
    with pytest.raises(PhysicsRangeError, match="T = -5.0 K"):
        Stream(m_dot=1, T=np.array([300.0, -5.0]), p=1e5)


def test_numbers_become_python_floats_and_limits_include_non_finite_values():
    """Integers and NumPy scalars are stored as ``float``; NaN and infinity are rejected."""
    stream = Stream(m_dot=1, T=np.float32(300), p=np.int64(100000))
    assert [type(value) for value in (stream.m_dot, stream.T, stream.p)] == [float] * 3
    assert type(stream.with_(p=np.float32(2e5)).p) is float
    for field in ({"m_dot": float("nan")}, {"T": float("inf")}, {"p": float("nan")}):
        with pytest.raises(PhysicsRangeError, match="expected"):
            Stream(**({"m_dot": 1, "T": 300, "p": 1e5} | field))


def test_unknown_and_missing_arguments_are_call_errors():
    """Constructor and ``with_`` reject unknown keywords with a suggestion."""
    with pytest.raises(CallError, match="unknown argument 'Temp'"):
        Stream(m_dot=1, Temp=300, p=1e5)
    with pytest.raises(CallError, match="did you mean 'fluid'"):
        Stream(m_dot=1, T=300, p=1e5, flui=WATER)
    with pytest.raises(CallError, match="missing argument p"):
        Stream(m_dot=1, T=300)
    with pytest.raises(CallError, match="did you mean 'fluid'"):
        Stream(m_dot=1, T=300, p=1e5).with_(fluids=WATER)


def test_fluids_are_validated():
    """A mapping builds a ``Fluid``; ``with_`` validates a new fluid; a bare string is rejected."""
    assert Stream(m_dot=1, T=300, p=1e5, fluid={"kind": "water"}).fluid == WATER
    assert Stream(m_dot=1, T=300, p=1e5).with_(fluid={"kind": "water"}).fluid == WATER
    with pytest.raises(CallError, match="expected a Fluid"):
        Stream(m_dot=1, T=300, p=1e5, fluid="brine")
    with pytest.raises(CallError, match="expected a Fluid"):
        Stream(m_dot=1, T=300, p=1e5).with_(fluid="brine")


def test_with_reuses_the_fluid_and_is_frozen():
    """A copy shares the fluid object; assignment to a stream raises."""
    stream = Stream(m_dot=1, T=300, p=1e5, fluid=WATER)
    assert stream.with_(T=310).fluid is stream.fluid
    with pytest.raises(FrozenInstanceError):
        stream.T = 310


def test_value_semantics_and_copies():
    """Equality, hash, repr, pickling, ``copy`` and ``deepcopy`` follow the values."""
    stream = Stream(m_dot=1, T=300, p=1e5, fluid=WATER)
    same = Stream(m_dot=1.0, T=300.0, p=1e5, fluid=WATER)
    assert stream == same and hash(stream) == hash(same) and stream != stream.with_(T=301)
    assert "m_dot=1.0" in repr(stream)
    for clone in (pickle.loads(pickle.dumps(stream)), copy.copy(stream), copy.deepcopy(stream)):
        assert clone == stream


def test_json_round_trip_keeps_the_event_log_layout():
    """The JSON of a stream lists ``m_dot``, ``T``, ``p`` and the fluid, and builds it back."""
    stream = Stream(m_dot=2, T=300, p=1e5, fluid=WATER)
    data = to_jsonable_python(stream)
    assert data == {
        "m_dot": 2.0,
        "T": 300.0,
        "p": 100000.0,
        "fluid": WATER.model_dump(mode="json"),
    }
    assert list(data) == ["m_dot", "T", "p", "fluid"]
    assert Stream(**json.loads(json.dumps(data))) == stream


def test_text_of_a_stream_lists_its_fields():
    """``str`` is the field listing printed by examples; every fluid fraction is a float."""
    stream = Stream(m_dot=1, T=300, p=1e5, fluid=BRINE)
    assert str(stream) == f"m_dot=1.0 T=300.0 p=100000.0 fluid={stream.fluid!r}"
    assert isinstance(BRINE.gas_mass_fraction, float)
