"""Backend registry, setting, automatic choice and NumPy fallback."""

import numpy as np
import pytest

from gemini import backends
from gemini.errors import UnknownNameError


def test_automatic_choice_follows_the_values():
    """Arrays select NumPy and scalars Python; a setting overrides the choice and restores it."""
    assert backends.select((1.0, 2)).name == "python"
    assert backends.select((np.ones(3), 2.0)).name == "numpy"
    with backends.settings("numpy"):
        assert backends.select((1.0,)).name == "numpy"
        with backends.settings():
            assert backends.select((1.0,)).name == "python"
    assert backends.select((1.0,)).name == "python"


def test_unknown_backend_names_raise():
    """A misspelled backend name suggests the registered one."""
    with pytest.raises(UnknownNameError, match="did you mean 'numpy'"):
        backends.settings("nunpy")


def test_missing_op_falls_back_to_numpy_and_registration_selects_by_name():
    """A backend without an op uses NumPy's; a registered backend is found by its name."""

    class Partial(backends.Backend):
        name = "partial"

        def add(self, left, right):
            return "own"

    partial = backends.register(Partial())
    try:
        assert backends.get("partial") is partial
        assert backends.implementation(partial, "add")(1, 2) == "own"
        assert backends.implementation(partial, "mul")(np.ones(2), 3).tolist() == [3, 3]
    finally:
        backends.base._BACKENDS.pop("partial")
