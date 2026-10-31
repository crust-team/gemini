"""Reductions over the last axis and ``interp``, which equals ``numpy.interp`` bit for bit."""

import math

import numpy as np

from gemini import ops, runtime

XP = [0.0, 1.0, 2.5, 4.0]
FP = [1.0, 3.0, 2.0, -1.0]


def test_reductions_on_sequences_and_arrays():
    """Sequences use Python, arrays NumPy, over the last axis."""
    assert ops.sum([1.0, 2.0, 3.5]) == 6.5 and ops.mean([1.0, 2.0, 3.0]) == 2.0
    assert ops.cumsum([1.0, 2.0, 3.5]) == [1.0, 3.0, 6.5]
    assert math.isnan(ops.mean([]))
    grid = np.array([[1.0, 2.0], [3.0, 5.0]])
    assert ops.sum(grid).tolist() == [3.0, 8.0] and ops.mean(grid).tolist() == [1.5, 4.0]
    assert ops.cumsum(grid).tolist() == [[1.0, 3.0], [3.0, 8.0]]


def test_interp_scalar_has_the_bits_of_numpy_interp():
    """Inside, outside, on a knot, at the ends and for NaN the scalar path equals ``np.interp``."""
    generator = np.random.default_rng(1)
    points = [*generator.uniform(-1.0, 5.0, 200), *XP, -1.0, 5.0, 1e-300, math.nan]
    for x in points:
        expected = np.interp(x, XP, FP)
        got = ops.interp(float(x), XP, FP)
        assert got == expected or (math.isnan(got) and math.isnan(expected))
        assert np.float64(got).tobytes() == np.float64(expected).tobytes()


def test_interp_on_arrays_and_non_finite_data():
    """The NumPy backend is ``np.interp``; infinite ordinates follow the same fallback."""
    x = np.array([-1.0, 0.5, 1.0, 3.0, 9.0])
    assert ops.interp(x, np.array(XP), np.array(FP)).tolist() == np.interp(x, XP, FP).tolist()
    with runtime.settings("numpy"):
        assert ops.interp(0.5, XP, FP) == np.interp(0.5, XP, FP)
    infinite = [0.0, math.inf, math.inf, 1.0]
    for value in (0.5, 1.5, 2.0):
        assert ops.interp(value, [0.0, 1.0, 2.0, 3.0], infinite) == np.interp(
            value, [0.0, 1.0, 2.0, 3.0], infinite
        )
