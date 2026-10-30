"""Run one scenario on every backend and compare what each reports with the reference.

``BACKENDS`` is the one list of backends under test: the first is the reference and every other
one is compared with it. Every parity test loops over this list and none names a backend, so a new
backend is added here and nowhere else. ``on_each_backend`` runs a callable once per backend,
with the backend forced for the whole call (tracing included), and returns the results by name.
"""

import contextlib

import numpy as np

from gemini import backends

BACKENDS = ("python", "numpy")
"""The backends under test; the first is the reference."""

REFERENCE = BACKENDS[0]


@contextlib.contextmanager
def forced(backend):
    """Force ``backend`` for the block, as ``gemini.backends.settings`` does."""
    with backends.settings(backend=backend):
        yield


def on_each_backend(scenario):
    """Return ``{backend: scenario(backend)}`` with each backend forced during its call."""
    outcomes = {}
    for backend in BACKENDS:
        with forced(backend):
            outcomes[backend] = scenario(backend)
    return outcomes


def others(outcomes):
    """Return ``(name, outcome)`` of every backend but the reference."""
    return [(name, outcome) for name, outcome in outcomes.items() if name != REFERENCE]


def assert_same_values(actual, expected, label, rtol):
    """Assert two arrays or scalars are equal within ``rtol`` (NaN equal to NaN)."""
    np.testing.assert_allclose(
        np.asarray(actual, dtype=float),
        np.asarray(expected, dtype=float),
        rtol=rtol,
        atol=0,
        equal_nan=True,
        err_msg=label,
    )
