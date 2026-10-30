"""The ``Backend`` base class, the backend registry and the context-local backend setting."""

from contextvars import ContextVar

import numpy as np

from gemini.errors import ValidationError
from gemini.utils.context import ContextSetting
from gemini.utils.strings import did_you_mean, join_names

_BACKENDS = {}
_selected = ContextVar("gemini_backend", default=None)
forced_name = _selected.get
"""Return the name set by ``settings(backend=...)``, else ``None``; a bound ``ContextVar.get``."""


def quiet(function, *values):
    """Return ``function`` of ``values`` with floating-point warnings silenced."""
    with np.errstate(all="ignore"):
        return function(*values)


class Backend:
    """Evaluate ops on one kind of value; subclasses define one method per op name.

    A method receives concrete values only and has the op's name, for example
    ``add(left, right)``. An op a backend does not define runs on the NumPy backend.
    ``where(condition, if_true, if_false)`` receives both branches as plain values (or ``None``),
    so every op must return ``inf`` or ``nan`` on an operand that is invalid in a branch that is
    not selected, never raise and never warn.
    """

    name = None


def register(backend):
    """Make ``backend`` selectable by its name and return it."""
    _BACKENDS[backend.name] = backend
    return backend


def get(name):
    """Return the registered backend called ``name``."""
    if name not in _BACKENDS:
        raise ValidationError(
            f"backends: backend = {name!r}; expected one of {join_names(_BACKENDS)}"
            f"{did_you_mean(name, _BACKENDS)}",
            code="unknown_name",
        )
    return _BACKENDS[name]


def settings(backend=None):
    """Select a backend by name within a ``with`` block or decorated call.

    ``None`` restores the automatic choice from the values (see ``select``).
    """
    if backend is not None:
        get(backend)
    return ContextSetting(_selected, lambda current: backend)


def select(values):
    """Return the selected backend, else NumPy for any array argument, else Python."""
    name = _selected.get()
    if name is not None:
        return get(name)
    for value in values:
        if isinstance(value, np.ndarray):
            return _BACKENDS["numpy"]
    return _BACKENDS["python"]


def implementation(backend, op_name):
    """Return the method of ``backend`` for ``op_name``, falling back to the NumPy backend."""
    method = getattr(backend, op_name, None)
    if method is not None:
        return method
    return getattr(get("numpy"), op_name)
