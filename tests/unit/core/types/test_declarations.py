"""Ready-made declaration validation."""

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

    def forward(self, inlet, command, weather):
        """Return the inlet after recording a value."""
        self.value = command + weather
        return inlet


def test_parameter_units_shape_and_metadata():
    """Parameters validate units and vector shape once assigned."""
    module = Declared(length="1200 m", coefficients=[1, 2])
    assert module.length == 1200
    assert module.get_parameter("length").unit == "m"
    with pytest.raises(TypeError, match="shape"):
        Declared(length=1, coefficients=[1])
    with pytest.raises(TypeError, match="expected m"):
        Declared(length="12 bar", coefficients=[1, 2])


def test_all_sections_list_own_declarations():
    """Section listings expose declaration objects without duplicate schemas."""
    module = Declared(length=1, coefficients=[1, 2])
    assert list(module.inlets()) == ["inlet"]
    assert list(module.controls()) == ["command"]
    assert list(module.boundaries()) == ["weather"]
    assert list(module.inputs()) == ["command", "weather"]
    assert list(module.outputs()) == ["value"]
    assert list(module.outlets()) == ["outlet"]
