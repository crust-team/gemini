"""Immutable named fluid-port mappings."""

import numpy as np
import pytest

from gemini.core.types import BRINE, Ports, Stream
from gemini.errors import UnknownPortError


@pytest.fixture
def streams():
    """Return two distinct streams for mapping tests."""
    return (
        Stream(m_dot=1, T=300, p=1e5),
        Stream(m_dot=2, T=310, p=2e5),
    )


def test_mapping_attributes_and_declaration_order(streams):
    """Ports expose the complete Mapping API and attribute access in input order."""
    suction, return_stream = streams
    ports = Ports({"suction": suction, "return_stream": return_stream}, path="plant.pump")

    assert ports["suction"] is suction
    assert ports.suction is suction
    assert "return_stream" in ports
    assert len(ports) == 2
    assert list(ports) == ["suction", "return_stream"]
    assert list(ports.keys()) == ["suction", "return_stream"]
    assert list(ports.values()) == [suction, return_stream]
    assert list(ports.items()) == [
        ("suction", suction),
        ("return_stream", return_stream),
    ]


def test_unknown_names_include_path_valid_names_and_suggestion(streams):
    """Mapping and attribute misses explain the owning module and nearest port."""
    ports = Ports({"suction": streams[0]}, path="plant.esp")

    with pytest.raises(
        AttributeError, match="plant.esp.*suctoin.*valid names: suction.*did you mean 'suction'"
    ):
        ports.suctoin
    with pytest.raises(UnknownPortError, match="plant.esp.*discharge.*valid names: suction"):
        ports["discharge"]


def test_ports_are_immutable_and_copy_the_source_mapping(streams):
    """Neither mapping syntax, attributes nor later source edits can mutate Ports."""
    source = {"suction": streams[0]}
    ports = Ports(source, path="pump")
    source["suction"] = streams[1]

    assert ports.suction is streams[0]
    with pytest.raises(TypeError):
        ports["suction"] = streams[1]
    with pytest.raises(TypeError):
        del ports["suction"]
    with pytest.raises(AttributeError, match="immutable"):
        ports.suction = streams[1]
    with pytest.raises(AttributeError, match="immutable"):
        del ports.suction


def test_ports_reject_non_stream_values(streams):
    """The port mapping never carries scalar controls or computed outputs."""
    with pytest.raises(TypeError, match="plant.esp.*suction.*Stream.*valid names: suction"):
        Ports({"suction": 1.0}, path="plant.esp")


def test_ports_accept_streams_of_arrays():
    """Batched calls pass ``Stream`` values of arrays through the same mapping."""
    state = Stream(m_dot=np.array([1.0, 2.0]), T=300.0, p=1e5, fluid=BRINE)
    assert Ports({"inlet": state}).inlet is state


def test_trusted_ports_equal_checked_ports_and_stay_immutable(streams):
    """The unchecked constructor of the engine gives the same mapping, read-only."""
    values = {"suction": streams[0], "return_stream": streams[1]}
    trusted = Ports._trusted(dict(values), "plant.pump")
    assert dict(trusted) == dict(Ports(values, path="plant.pump")) == values
    assert trusted._unknown("suction") == Ports(values, path="plant.pump")._unknown("suction")
    with pytest.raises(AttributeError, match="immutable"):
        trusted.suction = streams[1]
