"""The setting that turns the traced replay path off, for debugging and comparison."""

from contextvars import ContextVar

from gemini.utils.context import ContextSetting

_traced = ContextVar("graph_traced", default=True)


def settings(traced=None):
    """Enable or disable the traced replay within a ``with`` block or decorated call.

    ``traced=False`` makes ``Engine.replay`` evaluate every twin tick by tick on the plain path;
    ``None`` keeps the current choice and the default is on. It is not part of ``gm.runtime``,
    so checkpoints do not store it.
    """
    return ContextSetting(_traced, lambda current: current if traced is None else traced)


def traced_enabled():
    """Return whether the engine may evaluate replay twins through the graph."""
    return _traced.get()
