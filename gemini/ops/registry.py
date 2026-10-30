"""The op registry: the name, kind and operand count of every op.

The registry only describes ops; backends implement them (``gemini.backends``) and the graph
records them. The kind is what graph passes rely on: ``elementwise`` ops apply row by row,
``index`` selects one item of a vector parameter, ``check`` produces per-row error codes and
``scan`` carries state from step to step. ``reduction``, ``interp`` and ``solver`` are the kinds
of the design that no op uses yet.
"""

from dataclasses import dataclass

from gemini.errors import UnknownNameError
from gemini.utils.strings import did_you_mean

KINDS = ("elementwise", "index", "reduction", "interp", "check", "solver", "scan")

_OPS = {}


@dataclass(frozen=True)
class OpDef:
    """One registered op: its ``name``, ``kind`` and number of operands ``arity``."""

    name: str
    kind: str
    arity: int


def register(name, kind, arity):
    """Register an op and return its definition; the kind must be one of ``KINDS``."""
    if kind not in KINDS:
        raise UnknownNameError(f"ops.register: kind = {kind!r}; expected one of {KINDS}")
    _OPS[name] = OpDef(name, kind, arity)
    return _OPS[name]


def get(name):
    """Return the definition of the op called ``name``."""
    if name not in _OPS:
        raise UnknownNameError(f"ops: op = {name!r} is unknown{did_you_mean(name, _OPS)}")
    return _OPS[name]


def registered():
    """Return every op definition by name, in registration order."""
    return dict(_OPS)
