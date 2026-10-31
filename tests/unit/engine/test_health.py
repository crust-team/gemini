"""Health over the rows of a chunk: once on arrays, row by row where it must."""

import numpy as np
import pytest

from gemini import runtime
from gemini.engine.health import UNAVAILABLE, HealthColumns, assess
from gemini.errors import PhysicsError
from gemini.modules import Module
from gemini.modules.declarations import Output
from gemini.types import Health, ModuleResult, Ports, Values
from gemini.types.results import NOT_ASSESSED


class Gauge(Module):
    """A leaf with one output and a health whose score is the measured fraction."""

    def __init__(self):
        """Declare the output."""
        super().__init__()

        # Outputs
        self.value = Output(float)

    def forward(self, inlets):
        """Expose no fluid outlets."""

        outlets = dict()
        return outlets

    def health(self, result, measured):
        """Score the measured fraction; a flag of two is a bad measurement."""
        return Health(
            score=measured["fraction"],
            alarm=measured["fraction"] < 0.5,
            message="gauge",
            metrics={"value": result.outputs.value},
        )


def _result(values):
    return ModuleResult(outputs=Values({"value": np.asarray(values)}), outlets=Ports({}))


def test_a_module_without_diagnostics_is_unavailable():
    """It is not called; its health says so, with the message of a row that was not assessed."""
    health, errors = assess(Module(), _result([1.0, 2.0]), {}, 2)
    assert health is UNAVAILABLE and errors == {} and UNAVAILABLE.message == NOT_ASSESSED


def test_health_is_called_once_on_the_arrays_of_the_chunk():
    """The result is the module's own, with arrays for every field."""
    health, errors = assess(Gauge(), _result([1.0, 2.0]), {"fraction": np.array([0.2, 0.9])}, 2)
    assert errors == {} and health.alarm.tolist() == [True, False]
    assert health.metrics["value"].tolist() == [1.0, 2.0]


@pytest.mark.parametrize("backend", ["numpy", "python"])
def test_rows_whose_health_raises_fail_and_the_others_are_stacked(backend):
    """A score outside [0, 1] fails its row with the real error; the other rows keep theirs."""
    measured = {"fraction": np.array([0.2, 2.0, 0.9])}
    with runtime.settings(backend=backend):
        health, errors = assess(Gauge(), _result([1.0, 2.0, 3.0]), measured, 3)
    assert list(errors) == [1] and isinstance(errors[1], PhysicsError)
    assert isinstance(health, HealthColumns)
    assert health.score[[0, 2]].tolist() == [0.2, 0.9] and health.alarm[[0, 2]].tolist() == [
        True,
        False,
    ]
    assert health.metrics["value"][[0, 2]].tolist() == [1.0, 3.0]
