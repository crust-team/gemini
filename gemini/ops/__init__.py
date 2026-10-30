"""Ops that physics is written with, so one function runs on floats, arrays and traced values.

Arithmetic and comparisons come from the Python operators of the values themselves; the
functions here cover what operators cannot express: ``where`` instead of a value-dependent
``if``, ``check`` instead of ``if ...: raise``, ``logical_and``, ``logical_or`` and
``logical_not`` instead of ``and``, ``or`` and ``not``, ``maximum``, ``minimum`` and ``abs``
instead of ``max``, ``min`` and ``abs``, and the functions of ``math`` (``log``, ``sqrt``,
``exp``, ...), reductions and ``interp``.
``Constant`` declares a named constant that a trace records as a graph input.
"""

from gemini.ops import control
from gemini.ops.check import check
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
from gemini.ops.logic import eq, ge, gt, le, logical_and, lt, ne, where
from gemini.ops.math import add, floordiv, getitem, mod, mul, neg, pow, sub, truediv
from gemini.ops.reductions import cumsum, interp, mean, sum

__all__ = [
    "Constant",
    "Operators",
    "Symbolic",
    "abs",
    "acos",
    "add",
    "asin",
    "atan",
    "atan2",
    "ceil",
    "check",
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
    "pow",
    "round",
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
