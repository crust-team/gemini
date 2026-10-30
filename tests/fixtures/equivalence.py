"""Check that one source gives the same numbers on floats, arrays and traced graphs.

``assert_function_matches`` compares a physics function called once per row on Python floats
with one traced run on the stacked columns (``gemini.graph.run_function``), so an array row can
cross a ``where`` around a ``check`` as it does in the engine; a direct call on arrays raises at
the first failing row. ``assert_module_matches`` compares a module called once per row
with one traced call. ``RTOL`` is the documented tolerance of the NumPy backend against the
Python path; a ``None`` on the Python path is NaN on arrays. ``assert_same_error`` checks that a
failing row raises the same class and message on both paths, the graph's error being the first
failing row that reaches the result.
"""

import dataclasses
import math
from collections.abc import Mapping

import numpy as np
import pytest

from gemini.core.types import Stream
from gemini.graph import run, run_function

RTOL = 1e-12
STREAM_FIELDS = ("m_dot", "T", "p")


def flatten(value):
    """Return a result as a dict of named leaf values, for dataclasses, mappings and tuples."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, tuple):
        return dict(enumerate(value))
    return {"value": value}


def assert_close(actual, expected, label):
    """Compare per-row Python values ``expected`` with an array or scalar ``actual``.

    A row may be a list of numbers (a vector output); ``actual`` is then an array of shape
    ``(rows, length)``.
    """
    reference = np.array([math.nan if item is None else item for item in expected], dtype=float)
    actual = np.broadcast_to(np.asarray(actual, dtype=float), reference.shape)
    np.testing.assert_allclose(actual, reference, rtol=RTOL, atol=0, equal_nan=True, err_msg=label)


def assert_function_matches(function, rows, **fixed):
    """Assert ``function(*row, **fixed)`` per row equals one traced run on the stacked columns."""
    expected = [flatten(function(*row, **fixed)) for row in rows]
    columns = [np.array(column, dtype=float) for column in zip(*rows)]
    actual = flatten(run_function(function, *columns, **fixed))
    assert actual.keys() == expected[0].keys()
    for name, value in actual.items():
        assert_close(value, [row[name] for row in expected], f"{function.__name__}: {name}")


def assert_same_error(function, rows, error, **fixed):
    """Assert the first failing row raises the same ``error`` and message as the traced run."""
    with pytest.raises(error) as on_arrays:
        run_function(function, *(np.array(c, dtype=float) for c in zip(*rows)), **fixed)
    for row in rows:
        try:
            function(*row, **fixed)
        except error as on_floats:
            assert str(on_arrays.value) == str(on_floats)
            return
    pytest.fail(f"{function.__name__}: no row failed on Python floats")


def _stacked_stream(streams):
    return Stream(
        **{field: np.array([getattr(s, field) for s in streams]) for field in STREAM_FIELDS},
        fluid=streams[0].fluid,
    )


def assert_module_matches(module, rows, breaks=False):
    """Assert one traced call of ``module`` equals one call per row.

    Each row maps inlet names to ``Stream`` objects and control or boundary names to numbers.
    ``breaks=True`` accepts a graph break, for a module documented as one.
    """
    calls = [module(**row) for row in rows]
    inlets = {
        name: _stacked_stream([row[name] for row in rows]) for name in module.inlets() if rows
    }
    inputs = {
        name: np.array([row[name] for row in rows], dtype=float)
        for name in rows[0]
        if name not in inlets
    }
    traced = run(module, inlets, inputs)
    assert breaks or traced.breaks == [], traced.breaks
    for name in calls[0].outputs:
        values = [call.outputs[name] for call in calls]
        assert_close(traced.outputs[name], values, f"{module.path}.{name}")
    for port in module.outlets():
        for field in STREAM_FIELDS:
            values = [getattr(call.outlets[port], field) for call in calls]
            assert_close(traced.outlets[port][field], values, f"{module.path}.{port}.{field}")
