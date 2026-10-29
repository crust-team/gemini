"""Binding plans, boundary preparation and the measured and chained step functions."""

from collections import Counter

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.core.data.loader import Sample
from gemini.core.engine.step import BindingPlan, chained_step, prepare, twin_step
from gemini.core.modules import Module
from gemini.core.types import (
    Control,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Pressure,
    Stream,
    Temperature,
)
from gemini.core.types.bindings import Binding, ModuleBindings

TIME = pd.Timestamp("2024-01-01", tz="UTC")


class Tank(Module):
    """Leaf passing its inlet through; its mass-flow control may be bound volumetrically."""

    def __init__(self):
        """Declare a reference state, one stream and a mass-flow control."""
        super().__init__()

        # Parameters
        self.pressure = Parameter(Pressure)
        self.temperature = Parameter(Temperature)

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.m_dot = Control(MassFlow)

        # Outputs
        self.flow = Output(MassFlow)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the inlet stream through."""

        # Outlets
        outlet = inlets.inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        if self.m_dot < 0:
            raise ValueError("negative flow")
        self.flow = self.m_dot


class Valve(Module):
    """Leaf with a mass-flow control but no reference state."""

    def __init__(self):
        """Declare one control and one output."""
        super().__init__()

        # Controls
        self.m_dot = Control(MassFlow)

        # Outputs
        self.flow = Output(MassFlow)

    def forward(self, inlets):
        """Expose no fluid outlets."""

        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.flow = self.m_dot


def tank(unit="kg/s"):
    """Return a configured tank bound to ``rate`` and inlet columns."""
    module = Tank()
    module.update_params(pressure=2e5, temperature=320.0)
    stream = {
        "m_dot": Binding(column="flow", unit="kg/s"),
        "p": Binding(column="p", unit="Pa"),
        "T": Binding(column="T", unit="K"),
    }
    module.bindings = {
        "": ModuleBindings(
            controls={"m_dot": Binding(column="rate", unit=unit)}, inlets={"inlet": stream}
        )
    }
    return module


def dataset(**columns):
    """Return a one-row dataset with the given column values."""
    return gm.Dataset.from_dict({k: [v] for k, v in columns.items()}, [TIME])


def sample(**row):
    """Return one sample at the test time."""
    return Sample(TIME.to_pydatetime(), 900.0, row)


ROW = dict(rate=2.0, flow=10.0, p=3e5, T=330.0)


def test_prepare_converts_volumetric_controls_with_the_module_reference_state():
    """A kg/s control bound in m3/h uses the fluid density at the module's pressure/temperature."""
    module = tank("m3/h")
    kwargs, measured = prepare(module, module.bindings[""], ROW)
    density = module.fluid.properties(2e5, 320.0).density
    assert kwargs["m_dot"] == pytest.approx(2.0 / 3600 * density)
    assert kwargs["inlet"].m_dot == 10.0 and kwargs["inlet"].T == 330.0
    assert measured == {}


def test_replay_plan_selects_twins_and_takes_units_from_the_dataset(fresh_plant, reference_dataset):
    """The composite root is not a twin; ``only`` selects twins; dataset units win."""
    plan = BindingPlan(fresh_plant, reference_dataset, "replay")
    paths = [path for path, *_ in plan.entries]
    assert "" not in paths and "doublet.esp" in paths
    only = BindingPlan(fresh_plant, reference_dataset, "replay", only=["doublet.esp"])
    assert [path for path, *_ in only.entries] == ["doublet.esp"]
    assert "doublet.esp.frequency" in only.columns
    module = tank()
    data = gm.Dataset.from_dict({k: [v] for k, v in ROW.items()}, [TIME], units={"rate": "t/h"})
    (_, _, bound, _), *_ = BindingPlan(module, data, "replay").entries
    assert bound.controls["m_dot"].unit == "t/h"
    assert module.bindings[""].controls["m_dot"].unit == "kg/s"


def test_plan_rejects_bad_selections_and_missing_columns(fresh_plant, reference_dataset):
    """Unknown ``only`` paths and all absent columns fail before the first step."""
    with pytest.raises(gm.errors.BindingError, match="only path = 'doublet'"):
        BindingPlan(fresh_plant, reference_dataset, "replay", only=["doublet"])
    with pytest.raises(gm.errors.BindingError, match="flow, p"):
        BindingPlan(tank(), dataset(rate=1.0, T=300.0), "replay")


def test_plan_rejects_volumetric_flows_it_cannot_convert():
    """Volumetric flows need a reference state (controls) or p and T (inlets)."""
    valve = Valve()
    valve.bindings = {"": ModuleBindings(controls={"m_dot": Binding(column="rate", unit="m3/h")})}
    with pytest.raises(gm.errors.BindingError, match="pressure and temperature parameters"):
        BindingPlan(valve, dataset(rate=1.0), "replay")
    module = tank()
    module.bindings[""].inlets["inlet"]["m_dot"].unit = "m3/s"
    del module.bindings[""].inlets["inlet"]["p"]
    with pytest.raises(gm.errors.BindingError, match=r"inlet.m_dot = 'flow' \[m3/s\]"):
        BindingPlan(module, dataset(**ROW), "replay")


def test_simulation_plan_requires_a_column_or_default_for_every_input():
    """A leaf input without data or default fails; bound inputs become chained inputs."""
    module = tank()
    with pytest.raises(gm.errors.BindingError, match="simulation inputs = m_dot"):
        BindingPlan(module, dataset(flow=10.0, p=3e5, T=330.0), "simulate")
    plan = BindingPlan(module, dataset(**ROW), "simulate")
    assert [(path, list(bound.controls)) for path, _, bound in plan.chained_inputs] == [
        ("", ["m_dot"])
    ]
    assert plan.columns == {"rate", "flow", "p", "T"}


def test_twin_step_returns_outputs_skips_and_errors():
    """Missing data is a counted skip; failures are recorded, or raised as StepError."""
    module = tank()
    plan = BindingPlan(module, dataset(**ROW), "replay")
    outputs, skips, errors = twin_step(module, sample(**ROW), {}, plan)
    assert outputs[""][0].outputs.flow == 2.0 and (skips, errors) == ({}, [])
    outputs, skips, errors = twin_step(module, sample(**ROW | {"p": np.nan}), {}, plan)
    assert outputs == {} and skips == {"": Counter({"p": 1})}
    _, _, errors = twin_step(module, sample(**ROW | {"rate": -1.0}), {}, plan)
    assert errors == [dict(module="", message="negative flow", type="ValueError")]
    plan.on_error = "raise"
    with pytest.raises(gm.errors.StepError, match="negative flow") as raised:
        twin_step(module, sample(**ROW | {"rate": -1.0}), {}, plan)
    assert isinstance(raised.value.__cause__, ValueError)


def test_chained_step_skips_the_plant_when_data_is_missing():
    """Simulation counts missing data as a skip of the plant, as replay does for twins."""
    module = tank()
    plan = BindingPlan(module, dataset(**ROW), "simulate")
    outputs, skips, errors = chained_step(module, sample(**ROW), {}, plan)
    assert outputs[""][0].outputs.flow == 2.0 and (skips, errors) == ({}, [])
    outputs, skips, errors = chained_step(module, sample(**ROW | {"rate": np.nan}), {}, plan)
    assert (outputs, skips, errors) == ({}, {"": Counter({"rate": 1})}, [])


def test_dated_parameters_apply_once_per_transition(fresh_plant, reference_dataset):
    """Parameters are applied at the first tick and again only at the next snapshot date."""
    calls = []
    plan = BindingPlan(fresh_plant, reference_dataset, "replay")
    plan._dates = [TIME + pd.Timedelta(hours=1)]

    class Recorder:
        """Record parameter application instants."""

        def apply_params_at(self, at):
            """Remember the instant."""
            calls.append(at)

    for minutes in (0, 30, 60, 90):
        plan.apply_parameters(Recorder(), TIME + pd.Timedelta(minutes=minutes))
    assert calls == [TIME, TIME + pd.Timedelta(hours=1)]
