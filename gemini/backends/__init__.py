"""Backends that evaluate ops: ``python`` for scalars and ``numpy`` for arrays.

``select(values)`` picks the backend of ``settings(backend=...)`` when one is set, otherwise
NumPy for array arguments and Python for scalars. An op missing in a backend runs on NumPy.
``forced_name()`` is the cheap test of whether a setting is active: ops on plain Python scalars
skip the backend selection entirely when it returns ``None``.
"""

from gemini.backends.base import (
    Backend,
    forced_name,
    get,
    implementation,
    register,
    select,
    settings,
)
from gemini.backends.numpy import NumpyBackend
from gemini.backends.python import PythonBackend
from gemini.backends.scalars import PLAIN, WRAP, scope_mode

register(PythonBackend())
register(NumpyBackend())

__all__ = [
    "Backend",
    "PLAIN",
    "WRAP",
    "forced_name",
    "get",
    "implementation",
    "register",
    "scope_mode",
    "select",
    "settings",
]
