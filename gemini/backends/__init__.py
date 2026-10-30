"""Backends that evaluate ops: ``python`` for scalars and ``numpy`` for arrays.

``select(values)`` picks the backend of ``settings(backend=...)`` when one is set, otherwise
NumPy for array arguments and Python for scalars. An op missing in a backend runs on NumPy.
"""

from gemini.backends.base import Backend, get, implementation, register, select, settings
from gemini.backends.numpy import NumpyBackend
from gemini.backends.python import PythonBackend

register(PythonBackend())
register(NumpyBackend())

__all__ = ["Backend", "get", "implementation", "register", "select", "settings"]
