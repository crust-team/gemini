"""The compiler: trace a plant into a computation graph and register it as an executor.

Importing this package registers ``compile`` as the executor an ``Engine`` built with
``compile=True`` uses (``gemini.engine.executor.register_executor``); nothing else in the
package depends on it. ``compile(plant)`` returns the executor of a plant. The design is described
in ``.claude/docs/native-engine.md``.
"""

from gemini.compiler.executor import compile
from gemini.engine.executor import COMPILED, register_executor

register_executor(COMPILED, compile)

__all__ = ["compile"]
