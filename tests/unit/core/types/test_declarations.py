"""Ready-made declaration validation."""

import copy
import pickle
from datetime import datetime, timezone

import pytest

from gemini.core.modules import Module
from gemini.core.types import (
    UNSET,
    Boundary,
    Control,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Pressure,
    PressureDifference,
    Ratio,
    Stream,
    Temperature,
    TemperatureDifference,
)
from gemini.core.types.bindings import DatedParams
from gemini.errors import DeclarationError


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


def _declared(**params):
    """Return the fixture module with parameters set as explicit overrides."""
    module = Declared()
    module.update_params(**params)
    return module


def test_parameter_units_shape_and_metadata():
    """Parameters validate units and vector shape once assigned."""
    module = _declared(length="1200 m", coefficients=[1, 2])
    assert module.length == 1200
    assert module.get_parameter("length").unit == "m"
    with pytest.raises(TypeError, match="shape"):
        _declared(length=1, coefficients=[1])
    with pytest.raises(TypeError, match="expected m"):
        _declared(length="12 bar", coefficients=[1, 2])


def test_parameter_history_projects_module_snapshots():
    """A parameter exposes its values from the module's canonical dated snapshots."""
    module = Declared()
    changed = datetime(2025, 1, 1, tzinfo=timezone.utc)
    module.param_history.extend(
        [
            DatedParams(params={"length": 1, "coefficients": [1, 2]}),
            DatedParams(valid_from=changed, params={"length": 2, "coefficients": [3, 4]}),
        ]
    )
    assert module.get_parameter("length").history == [(None, 1.0), (changed, 2.0)]


def test_all_sections_list_own_declarations():
    """Section listings expose declaration objects without duplicate schemas."""
    module = _declared(length=1, coefficients=[1, 2])
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


def test_unset_keeps_its_identity_through_copy_and_pickle():
    """Copied and pickled modules still report unset parameters as missing."""
    assert copy.copy(UNSET) is UNSET
    assert copy.deepcopy(UNSET) is UNSET
    assert pickle.loads(pickle.dumps(UNSET)) is UNSET
    parameter = Parameter(Length)
    assert not copy.deepcopy(parameter).initialized
    assert copy.deepcopy(Declared()).missing_parameters() == ["length", "coefficients"]


def test_difference_parameters_ignore_unit_offsets():
    """A temperature difference given in degC is the same number of kelvin."""
    assert Parameter(TemperatureDifference).validate("5 degC") == 5
    assert Parameter(PressureDifference).validate("2 barg") == 2e5
    assert Parameter(Temperature).validate("5 degC") == 278.15


def test_unitless_declarations_keep_text_values():
    """Text with a trailing word is not a unit when the declaration has no unit."""
    assert Parameter(str, default="x").validate("12 m") == "12 m"
    assert Parameter(str, default="x").validate("2 stages") == "2 stages"


def test_invalid_values_raise_declaration_errors():
    """Wrong units and wrong shapes name the declaration path, value and expectation."""
    parameter = Parameter(Length).bind(None, "length")
    with pytest.raises(DeclarationError, match="length: invalid parameter value '12 bar'.*m"):
        parameter.validate("12 bar")
    with pytest.raises(DeclarationError, match="coefficients: shape = \\(1,\\); expected \\(2,\\)"):
        Parameter(list[float], shape=(2,)).bind(None, "coefficients").validate([1])
    with pytest.raises(DeclarationError, match="outlet.mdot: unknown stream field.*'m_dot'"):
        Outlet(Stream).bind(None, "outlet").field("mdot")


def test_limits_come_from_the_quantity_and_the_bounds():
    """Quantity bounds and declared bounds merge; kinds without bounds give nothing."""
    assert Control(Pressure, le=9).limits() == {"ge": 0, "le": 9}
    assert Output(Temperature).limits() == {"gt": 0}
    assert Output(list[Pressure]).limits() == {"ge": 0}
    assert Output(bool).limits() == {}
    assert Output(Ratio | None).accepts_none() and not Output(float).accepts_none()
    assert Inlet(Stream).limits() == {}
