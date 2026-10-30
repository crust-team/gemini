"""Binding plans: which twins a run evaluates, their sources and the columns they need."""

import pandas as pd

import gemini as gm
from gemini.engine.step import BindingPlan
from gemini.types.bindings import Binding, ModuleBindings
from tests.fixtures.engine_tank import ROW, TIME, Valve, dataset, tank
from tests.fixtures.errors import raises


def test_replay_plan_selects_twins_and_takes_units_from_the_dataset(fresh_plant, reference_dataset):
    """The composite root is not a twin; ``only`` selects twins; dataset units win."""
    plan = BindingPlan(fresh_plant, reference_dataset, "replay")
    paths = [twin.path for twin in plan.twins]
    assert "" not in paths and "doublet.esp" in paths
    only = BindingPlan(fresh_plant, reference_dataset, "replay", only=["doublet.esp"])
    assert [twin.path for twin in only.twins] == ["doublet.esp"]
    assert "doublet.esp.frequency" in only.columns
    module = tank()
    data = gm.Dataset.from_dict({k: [v] for k, v in ROW.items()}, [TIME], units={"rate": "t/h"})
    (twin,) = BindingPlan(module, data, "replay").twins
    assert twin.inputs()[0].binding.unit == "t/h"
    assert module.bindings[""].controls["m_dot"].unit == "kg/s"


def test_plan_rejects_bad_selections_and_missing_columns(fresh_plant, reference_dataset):
    """Unknown ``only`` paths and all absent columns fail before the first step."""
    with raises(gm.errors.ValidationError, "invalid_binding", match="only path = 'doublet'"):
        BindingPlan(fresh_plant, reference_dataset, "replay", only=["doublet"])
    with raises(gm.errors.ValidationError, "missing_column", match="flow, p") as caught:
        BindingPlan(tank(), dataset(rate=1.0, T=300.0), "replay")
    assert isinstance(caught.value, gm.errors.ValidationError)
    assert caught.value.code == "missing_column"


def test_plan_rejects_volumetric_flows_it_cannot_convert():
    """Volumetric flows need a reference state (controls) or p and T (inlets)."""
    valve = Valve()
    valve.bindings = {"": ModuleBindings(controls={"m_dot": Binding(column="rate", unit="m3/h")})}
    with raises(
        gm.errors.ValidationError, "invalid_binding", match="pressure and temperature parameters"
    ):
        BindingPlan(valve, dataset(rate=1.0), "replay")
    module = tank()
    module.bindings[""].inlets["inlet"]["m_dot"].unit = "m3/s"
    del module.bindings[""].inlets["inlet"]["p"]
    with raises(
        gm.errors.ValidationError, "invalid_binding", match=r"inlet.m_dot = 'flow' \[m3/s\]"
    ):
        BindingPlan(module, dataset(**ROW), "replay")


def test_simulation_plan_requires_a_column_or_default_for_every_input():
    """A leaf input without data or default fails; bound inputs become chained inputs."""
    module = tank()
    with raises(gm.errors.ValidationError, "invalid_binding", match="simulation inputs = m_dot"):
        BindingPlan(module, dataset(flow=10.0, p=3e5, T=330.0), "simulate")
    plan = BindingPlan(module, dataset(**ROW), "simulate")
    (twin,) = plan.twins
    assert [source.key for source in twin.inputs()] == ["m_dot"] and twin.leaves
    assert plan.columns == {"rate", "flow", "p", "T"}


def test_parameter_stretches_follow_the_dated_transitions(fresh_plant, reference_dataset):
    """Ticks share a stretch until the first tick at or after a later date."""
    plan = BindingPlan(fresh_plant, reference_dataset, "replay")
    ticks = [(TIME + pd.Timedelta(minutes=minutes)).to_pydatetime() for minutes in (0, 30, 60, 90)]
    plan._dates = [TIME + pd.Timedelta(hours=1)]
    assert plan.parameter_stretches(ticks) == [(0, 2), (2, 4)]
    assert plan.parameter_stretches(ticks[:1]) == [(0, 1)]
