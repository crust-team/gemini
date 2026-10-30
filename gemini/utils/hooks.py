"""Ordered hook registrations that callers can remove again, and the read-only observer mark."""

import functools
import inspect

_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


class RemovableHandle:
    """Registration of one hook in an insertion-ordered dict; ``remove()`` may be called twice."""

    def __init__(self, hooks, hook):
        """Store ``hook`` in ``hooks`` under a fresh private key."""
        self._hooks = hooks
        self._key = object()
        hooks[self._key] = hook

    def remove(self):
        """Stop calling this hook; removing an already removed hook does nothing."""
        self._hooks.pop(self._key, None)


def has_signature(function, names):
    """Return whether ``function`` takes exactly ``names`` as required positional parameters."""
    parameters = inspect.signature(function).parameters
    if tuple(parameters) != tuple(names):
        return False
    return all(
        parameter.kind in _POSITIONAL and parameter.default is inspect.Parameter.empty
        for parameter in parameters.values()
    )


def observer(hook):
    """Mark a hook (a function or a ``functools.partial``) as read-only and return it.

    An observer never changes an output or a stream. The graph engine therefore does not call it
    on traced values: it replays the hook for every row of a batch after the arithmetic, with
    the values of that row.
    """
    hook._gemini_observer = True
    return hook


def is_observer(hook):
    """Return whether ``hook`` was marked with ``observer``, directly or through a partial."""
    if getattr(hook, "_gemini_observer", False):
        return True
    return isinstance(hook, functools.partial) and is_observer(hook.func)
