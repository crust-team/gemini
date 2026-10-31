"""The kernels that evaluate ops: ``python`` for scalars and ``numpy`` for arrays.

``select(values)`` picks the backend of ``gm.runtime.settings(backend=...)`` when one is set,
otherwise NumPy for array arguments and Python for scalars. An op missing in a backend runs on
NumPy. ``forced_name()`` is the cheap test of whether a setting is active: ops on plain Python
scalars skip the backend selection entirely when it returns ``None``.
"""

from gemini.ops.backend import Backend, forced_name, get, implementation, register, select
from gemini.ops.kernels.numpy import NumpyBackend
from gemini.ops.kernels.python import PythonBackend
from gemini.ops.kernels.scalars import PLAIN, WRAP, scope_mode

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
]
