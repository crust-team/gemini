"""Backend registry, setting, automatic choice and NumPy fallback."""

import numpy as np

from gemini import runtime
from gemini.errors import ValidationError
from gemini.ops import kernels
from gemini.ops.backend import _BACKENDS
from tests.fixtures.errors import raises


def test_automatic_choice_follows_the_values():
    """Arrays select NumPy and scalars Python; a setting overrides the choice and restores it."""
    assert kernels.select((1.0, 2)).name == "python"
    assert kernels.select((np.ones(3), 2.0)).name == "numpy"
    with runtime.settings("numpy"):
        assert kernels.select((1.0,)).name == "numpy"
        with runtime.settings(None):
            assert kernels.select((1.0,)).name == "python"
    assert kernels.select((1.0,)).name == "python"


def test_unknown_backend_names_raise():
    """A misspelled backend name suggests the registered one."""
    with raises(ValidationError, "unknown_name", match="did you mean 'numpy'"):
        runtime.settings("nunpy")


def test_missing_op_falls_back_to_numpy_and_registration_selects_by_name():
    """A backend without an op uses NumPy's; a registered backend is found by its name."""

    class Partial(kernels.Backend):
        name = "partial"

        def add(self, left, right):
            return "own"

    partial = kernels.register(Partial())
    try:
        assert kernels.get("partial") is partial
        assert kernels.implementation(partial, "add")(1, 2) == "own"
        assert kernels.implementation(partial, "mul")(np.ones(2), 3).tolist() == [3, 3]
    finally:
        _BACKENDS.pop("partial")
