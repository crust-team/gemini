"""The fixed stream-type list and the stream a port declares."""

import pytest

from gemini.errors import DefinitionError
from gemini.types import Inlet, Outlet, Stream, streams


def test_names_are_the_fixed_list():
    """The list is what the frontend colours."""
    assert streams.names() == ["brine", "hot_water", "chilled_water", "gas", "electricity", "fuel"]


def test_a_port_keeps_its_stream():
    """A port may name a stream type or take whatever flows through it."""
    assert Inlet(Stream, stream="brine").stream == "brine"
    assert Outlet(Stream).stream is None


def test_an_unknown_stream_suggests_the_closest():
    """A misspelt stream type fails while the class is built."""
    with pytest.raises(DefinitionError, match="did you mean 'brine'"):
        Inlet(Stream, stream="brin")
