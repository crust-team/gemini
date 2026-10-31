"""Solving a constraint: the free value of a plant, with the nodal doublet as the example."""

import pytest

import gemini as gm
from gemini import backends
from gemini.modules.plants._utils import constraints
from gemini.modules.plants._utils.plan import Solve
from tests.fixtures.parity import BACKENDS


def test_a_root_needs_a_sign_change():
    """Two ends of one sign raise and name the bracket."""
    with pytest.raises(gm.errors.PhysicsError, match="opposite signs"):
        constraints.root("solve", "rate", lambda value: value + 1.0, (0.0, 1.0))


def test_a_root_of_a_line_is_found():
    """The root comes from ``ops.brentq``."""
    found = constraints.root("solve", "rate", lambda value: value - 0.25, (0.0, 1.0))
    assert found == pytest.approx(0.25, abs=1e-11)


def test_a_root_is_a_number_on_every_backend():
    """A plant call is one row: a forced backend gives the solve no array."""
    for backend in BACKENDS:
        with backends.settings(backend=backend):
            found = constraints.root("solve", "rate", lambda value: float(value) - 0.25, (0.0, 1.0))
        assert found == pytest.approx(0.25, abs=1e-11)


def test_a_failing_trial_names_the_value():
    """A trial outside a model's domain says which value it was."""

    def residual(value):
        raise gm.errors.PhysicsError("out of the domain")

    with pytest.raises(gm.errors.PhysicsError, match="rate = 0.0 ; expected a trial"):
        constraints.root("solve", "rate", residual, (0.0, 1.0))


def test_constrain_takes_exactly_one_kind_of_value():
    """A target has a value to equal or to reach."""
    plant = gm.Plant("Solved")
    with pytest.raises(gm.errors.ValidationError, match="expected exactly one"):
        plant.constrain("a.b", by="c.d", bounds=(0, 1))


def test_the_constraints_of_an_opened_plant_join_its_parent():
    """A parent that opens a plant solves its constraints, with paths from the parent."""
    items = gm.plants.get("BoilerChpPlant")._compiled().items
    solves = [item for item in items if isinstance(item, Solve)]
    assert [item.constraint.by for item in solves] == [
        "doublet.reservoir.production_rate",
        "doublet.injection_pump.pressure_setpoint",
    ]
    assert [step.path for step in solves[0].steps] == [
        "doublet.reservoir",
        "doublet.well",
        "doublet.esp",
        "doublet.riser",
    ]
