"""The one error of tracing; internal to the graph, users never see it."""

from gemini.errors import GeminiError


class TraceError(GeminiError, TypeError):
    """A module cannot be traced into a graph, so it runs as a plain call (graph break)."""
