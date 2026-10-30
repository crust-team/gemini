"""The mode of the eager scalar scope, below the ops so that constants and backends can read it.

``scope_mode`` is ``None`` outside an eager physics scope (``gemini.ops.physics`` or a module
call), ``WRAP`` inside one that gives physics ``np.float64`` scalars, and ``PLAIN`` inside one that
leaves every value as it is (arrays, traced values, or a module that asks for it).
"""

from contextvars import ContextVar

WRAP = "wrap"
PLAIN = "plain"

scope_variable = ContextVar("gemini_scope_mode", default=None)
scope_mode = scope_variable.get
"""Return ``None``, ``WRAP`` or ``PLAIN``; a bound ``ContextVar.get``."""
