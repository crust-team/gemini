"""The SI columns of a twin, and the status that tells which ticks can be evaluated."""

import numpy as np
import pytest

import gemini as gm
from gemini.engine.columns import read
from gemini.engine.step import BindingPlan
from gemini.errors import PhysicsError
from gemini.types.bindings import Binding, ModuleBindings
from gemini.utils.data.loader import Aligned
from tests.fixtures.engine_tank import ROW, TIME, dataset, tank


def _read(module, **changes):
    """Return the block of the first twin over the columns of ``ROW`` with some replaced."""
    plan = BindingPlan(module, dataset(**ROW), "replay")
    columns = {
        name: np.asarray(changes.get(name, [value]), dtype=float) for name, value in ROW.items()
    }
    return read(plan.twins[0], _aligned(columns), 0, len(columns["rate"]))


def _aligned(columns):
    """Return aligned samples holding the given column arrays."""
    count = len(next(iter(columns.values())))
    return Aligned([TIME] * count, np.full(count, 900.0), columns)


def test_volumetric_controls_convert_with_the_module_reference_state():
    """A kg/s control bound in m3/h uses the fluid density at the module's pressure/temperature."""
    module = tank("m3/h")
    block = _read(module)
    density = module.fluid.properties(2e5, 320.0).density
    assert block.inputs["m_dot"][0] == pytest.approx(2.0 / 3600 * density)
    assert (
        block.fields["fluid_in", "m_dot"][0] == 10.0 and block.fields["fluid_in", "T"][0] == 330.0
    )
    assert block.status.tolist() == [0] and block.measured == {}


def test_the_first_missing_column_in_reading_order_is_the_skip_reason():
    """Controls come before inlet fields; a later missing value does not change the reason."""
    block = _read(tank(), rate=[np.nan], p=[np.nan])
    assert block.reasons == ["rate"] and block.status.tolist() == [1]
    assert block.selected.size == 0 and not block.applied.any()


def test_an_inlet_stream_the_limits_refuse_has_the_error_of_the_stream_constructor():
    """The error is the real ``PhysicsError`` of a ``Stream``; inputs are not applied."""
    block = _read(tank(), T=[-5.0, 330.0], rate=[2.0, 2.0], flow=[10.0] * 2, p=[3e5] * 2)
    assert block.status.tolist() == [-1, 0]
    error = block.stream_error(0)
    assert isinstance(error, PhysicsError) and "T = -5.0 K" in str(error)
    assert block.applied.tolist() == [False, True]


def test_measured_differences_convert_without_unit_offsets():
    """A measured pressure drop bound in barg converts by scale only (E-physics-904)."""
    module = gm.modules.Filter()
    module.bindings = {
        "": ModuleBindings(measured={"pressure_drop": Binding(column="dp", unit="barg")})
    }
    plan = BindingPlan(module, gm.Dataset.from_dict({"dp": [0.5]}, [TIME]), "replay")
    block = read(plan.twins[0], _aligned({"dp": np.array([0.5])}), 0, 1)
    assert block.measured["pressure_drop"][0] == pytest.approx(5e4)
