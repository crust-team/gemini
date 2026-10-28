"""Ready-made declaration validation."""

from datetime import datetime, timezone

import pytest

from gemini.core.modules import Module
from gemini.core.types import (
    Boundary,
    Control,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Stream,
)
from gemini.core.types.bindings import DatedParams


class Declared(Module):
    """Fixture containing every declaration kind."""

    def __init__(self):
        """Declare fields covering each declaration kind."""
        super().__init__()

        # Parameters
        self.length = Parameter(Length)
        self.coefficients = Parameter(list[float], shape=(2,))

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.command = Control(float, default=1)

        # Boundaries
        self.weather = Boundary(float)

        # Outputs
        self.value = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Return the inlet after recording a value."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.value = self.command + self.weather


def test_parameter_units_shape_and_metadata():
    """Parameters validate units and vector shape once assigned."""
    module = Declared(length="1200 m", coefficients=[1, 2])
    assert module.length == 1200
    assert module.get_parameter("length").unit == "m"
    with pytest.raises(TypeError, match="shape"):
        Declared(length=1, coefficients=[1])
    with pytest.raises(TypeError, match="expected m"):
        Declared(length="12 bar", coefficients=[1, 2])


def test_parameter_history_projects_module_snapshots():
    """A parameter exposes its values from the module's canonical dated snapshots."""
    module = Declared(length=1, coefficients=[1, 2])
    changed = datetime(2025, 1, 1, tzinfo=timezone.utc)
    module.param_history.append(
        DatedParams(valid_from=changed, params={"length": 2, "coefficients": [3, 4]})
    )
    assert module.get_parameter("length").history == [(None, 1.0), (changed, 2.0)]


def test_all_sections_list_own_declarations():
    """Section listings expose declaration objects without duplicate schemas."""
    module = Declared(length=1, coefficients=[1, 2])
    assert list(module.inlets()) == ["inlet"]
    assert list(module.controls()) == ["command"]
    assert list(module.boundaries()) == ["weather"]
    assert list(module.inputs()) == ["command", "weather"]
    assert list(module.outputs()) == ["value"]
    assert list(module.outlets()) == ["outlet"]


def test_inlets_and_outlets_accept_fluid_stream_types_only():
    """Scalar and energy values belong in inputs or outputs, never flow ports."""
    with pytest.raises(TypeError, match="fluid Stream"):
        Inlet(float)
    with pytest.raises(TypeError, match="fluid Stream"):
        Outlet(float)
