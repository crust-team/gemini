"""The order and wiring of the steps of a plant."""

import pytest

import gemini as gm
from gemini.modules.plants import plan


def test_split_end_splits_at_the_last_dot():
    """A port is the last part of an end."""
    assert plan.split_end("filters.hot.outlet") == ("filters.hot", "outlet")


def test_find_path_returns_the_modules_of_a_cycle_or_none():
    """A path needs at least one edge; a start can be its own goal."""
    edges = [("a", "b"), ("b", "c"), ("c", "a")]
    assert plan.find_path(edges, "a", "c") == ["a", "b", "c"]
    assert plan.find_path(edges, "a", "a") == ["a", "b", "c", "a"]
    assert plan.find_path(edges[:2], "a", "a") is None


def test_members_look_through_groups():
    """Group children are steps; the group itself is not."""
    plant = gm.Plant("Groups")
    plant.add("ModuleDict", "filters")
    plant.add("Filter", "filters.hot")
    plant.add("Filter", "single")
    assert [path for path, _ in plan.members(plant)] == ["filters.hot", "single"]


def test_the_plan_names_where_every_inlet_comes_from():
    """Steps take their streams from plant inlets or from an earlier step's outlet."""
    plant = gm.plants.library.build("Doublet")
    steps = plant._compiled()
    sink = next(step for step in steps.steps if step.path == "sink")
    assert sink.arguments == {"sandface": ("step", "injector", "bottom")}
    injector = steps.steps[0]
    assert injector.arguments == {"wellhead": ("inlet", "return_in")}
    assert steps.outlets == {"supply_out": ("riser", "wellhead")}


def test_state_connections_cannot_run_yet():
    """A plan with a state link raises ``NotImplementedYet``."""
    plant = gm.Plant("State")
    plant.add("Pipe", "one")
    plant.add("Pipe", "two")
    plant.connect("one.outlet", "two.inlet")
    plant.connect("two.outlet", "one.inlet", kind="state")
    with pytest.raises(gm.errors.NotImplementedYet):
        plan.compile_plan(plant)


def test_a_loop_through_a_plant_child_opens_it():
    """The doublet and a pipe form a cycle of composites, not of leaves: both are accepted."""
    plant = gm.Plant("Loop")
    plant.add("Doublet", "doublet")
    plant.add("Pipe", "pipe")
    plant.connect("doublet.supply_out", "pipe.inlet")
    plant.connect("pipe.outlet", "doublet.return_in")
    assert [step.path for step in plant._compiled().steps][-2:] == [
        "doublet.injector",
        "doublet.sink",
    ]
    assert plan.open_cycles(plant, plan.all_links(plant)) == {"doublet"}
