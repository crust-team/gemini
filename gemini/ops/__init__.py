"""Ops that physics is written with, so one function runs on floats, arrays and traced values.

Arithmetic and comparisons come from the Python operators of the values themselves; the
functions here cover what operators cannot express: ``where`` instead of a value-dependent
``if``, ``check`` instead of ``if ...: raise``, and ``logical_and`` instead of ``and``.
``Constant`` declares a named constant that a trace records as a graph input.
"""

from gemini.ops import control
from gemini.ops.check import check
from gemini.ops.dispatch import Constant, Operators, Symbolic, dispatch
from gemini.ops.logic import eq, ge, gt, le, logical_and, lt, ne, where
from gemini.ops.math import add, getitem, mul, neg, pow, sub, truediv

__all__ = [
    "Constant",
    "Operators",
    "Symbolic",
    "add",
    "check",
    "control",
    "dispatch",
    "eq",
    "ge",
    "getitem",
    "gt",
    "le",
    "logical_and",
    "lt",
    "mul",
    "ne",
    "neg",
    "pow",
    "sub",
    "truediv",
    "where",
]
