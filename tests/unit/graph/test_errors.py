"""``TraceError`` is internal to the graph."""

import gemini as gm
from gemini.graph.errors import TraceError


def test_trace_error_is_not_public():
    """A user never sees it: it is not in ``gm.errors``."""
    assert "TraceError" not in gm.errors.__all__ and not hasattr(gm.errors, "TraceError")
    assert issubclass(TraceError, gm.errors.GeminiError)
