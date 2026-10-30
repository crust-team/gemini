"""Ops that physics is written with, so one function runs on floats, arrays and traced values.

Arithmetic and comparisons come from the Python operators of the values themselves; the
functions here cover what operators cannot express: ``where`` instead of a value-dependent
``if``, ``check`` instead of ``if ...: raise``, ``logical_and``, ``logical_or`` and
``logical_not`` instead of ``and``, ``or`` and ``not``, ``maximum``, ``minimum`` and ``abs``
instead of ``max``, ``min`` and ``abs``, and the functions of ``math`` (``log``, ``sqrt``,
``exp``, ...), reductions, ``interp`` and the solvers ``brentq`` and ``newton``.
``Constant`` declares a named constant that a trace records as a graph input. ``physics`` decorates
a public function of ``core/physics`` so plain operators are safe in an eager call (see
``gemini.ops.scope``); ``Failed`` is the value of a function whose ``check`` failed there.
"""

from gemini.ops import control, scope
from gemini.ops.check import any_nan, check, check_numbers
from gemini.ops.dispatch import Constant, Operators, Symbolic, dispatch
from gemini.ops.elementwise import (
    abs,
    acos,
    asin,
    atan,
    atan2,
    ceil,
    clip,
    cos,
    cosh,
    exp,
    expm1,
    floor,
    isfinite,
    isinf,
    isnan,
    log,
    log10,
    logical_not,
    logical_or,
    maximum,
    minimum,
    round,
    sign,
    sin,
    sinh,
    sqrt,
    tan,
    tanh,
)
from gemini.ops.failed import Failed
from gemini.ops.logic import eq, ge, gt, le, logical_and, lt, ne, where
from gemini.ops.math import add, floordiv, getitem, mod, mul, neg, pow, sub, truediv
from gemini.ops.reductions import cumsum, interp, mean, sum
from gemini.ops.scope import physics, require
from gemini.ops.solvers import brentq, newton

__all__ = [
    "Constant",
    "Failed",
    "Operators",
    "Symbolic",
    "abs",
    "acos",
    "add",
    "any_nan",
    "asin",
    "atan",
    "atan2",
    "brentq",
    "ceil",
    "check",
    "check_numbers",
    "clip",
    "control",
    "cos",
    "cosh",
    "cumsum",
    "dispatch",
    "eq",
    "exp",
    "expm1",
    "floor",
    "floordiv",
    "ge",
    "getitem",
    "gt",
    "interp",
    "isfinite",
    "isinf",
    "isnan",
    "le",
    "log",
    "log10",
    "logical_and",
    "logical_not",
    "logical_or",
    "lt",
    "maximum",
    "mean",
    "minimum",
    "mod",
    "mul",
    "ne",
    "neg",
    "newton",
    "physics",
    "require",
    "pow",
    "round",
    "scope",
    "sign",
    "sin",
    "sinh",
    "sqrt",
    "sub",
    "sum",
    "tan",
    "tanh",
    "truediv",
    "where",
]
