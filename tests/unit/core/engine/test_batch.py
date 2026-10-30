"""The batch evaluation of replay twins gives exactly the results of the plain path."""

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini import graph, ops
from gemini.core.engine.callbacks import AutoCheckpoint, Callback, EventLog
from gemini.core.modules import Module
from gemini.core.types import (
    Control,
    Electricity,
    Health,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Ratio,
    State,
    Stream,
)
from gemini.core.types.bindings import Binding, DatedParams, ModuleBindings
from gemini.errors import PhysicsRangeError, StepError

TICKS = pd.date_range("2024-01-01", periods=12, freq="15min", tz="UTC")


class Booster(Module):
    """Raise the pressure by ``level * gain``; refuse a negative level; report a health."""

    def __init__(self):
        """Declare a parameter, an inlet, a control, outputs and an outlet."""
        super().__init__()

        # Parameters
        self.gain = Parameter(float, default=2.0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.level = Control(float)

        # Outputs
        self.rise = Output(float)
        self.power = Output(Electricity)
        self.share = Output(Ratio | None, soft_sensor=True)
        self.inverse = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Raise the pressure."""

        # Outlets
        ops.check(
            self.level >= 0,
            PhysicsRangeError,
            "{path}: level = {level}",
            path=self.path,
            level=self.level,
        )
        outlet = inlets.inlet.with_(p=inlets.inlet.p + self.level * self.gain)
        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.rise = outlets.outlet.p - inlets.inlet.p
        self.power = self.rise * inlets.inlet.m_dot
        self.share = ops.where(self.level == 0, None, self.rise / ops.maximum(self.level, 1e-9))
        self.inverse = ops.truediv(1.0, self.level)

    def health(self, result, measured):
        """Compare the rise with the measured one."""
        error = abs(result.outputs.rise - measured["rise"])
        return Health(score=1 / (1 + error / 100), alarm=error > 5e4, message="rise")


class Reservoir(Module):
    """A stateful leaf: it carries the sum of the flows it saw."""

    def __init__(self):
        """Declare a state, an inlet, an output and an outlet."""
        super().__init__()

        # States
        self.total = State(float, default=0.0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.content = Output(float)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the stream."""

        # Outlets
        outlets = dict(outlet=inlets.inlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.content = self.total + inlets.inlet.m_dot

    def _advance_states(self, inlets, outlets, dt):
        return dict(total=self.content)


class Pair(Module):
    """Two boosters side by side, each a twin; the root is only a container."""

    def __init__(self):
        """Declare the children and the bindings of both twins."""
        super().__init__()

        # Modules
        self.first = Booster()
        self.second = Booster()
        self.tank = Reservoir()


def _inlet_bindings():
    return {
        "m_dot": Binding(column="flow", unit="m3/h"),
        "T": Binding(column="temperature", unit="°C"),
        "p": Binding(column="pressure", unit="bar"),
    }


def _bindings(path_prefix=""):
    return {
        f"{path_prefix}first": ModuleBindings(
            controls={"level": Binding(column="level", unit="bar")},
            inlets={"inlet": _inlet_bindings()},
            measured={"rise": Binding(column="rise", unit="bar")},
        ),
        f"{path_prefix}second": ModuleBindings(
            controls={"level": Binding(column="level2", unit="Pa")},
            inlets={"inlet": _inlet_bindings()},
            measured={"rise": Binding(column="rise", unit="bar")},
        ),
    }


def _plant(with_tank=False):
    plant = Pair()
    plant.bindings = _bindings()
    if with_tank:
        plant.bindings["tank"] = ModuleBindings(inlets={"inlet": _inlet_bindings()})
    return plant


def _dated_plant():
    plant = _plant()
    for module in (plant.first, plant.second):
        module.param_history = [
            DatedParams(params={"gain": 2.0}),
            DatedParams(valid_from=TICKS[6], params={"gain": 5.0}),
        ]
    return plant


def _frame(changes=None):
    rows = len(TICKS)
    frame = pd.DataFrame(
        {
            "flow": np.linspace(10.0, 20.0, rows),
            "temperature": np.linspace(60.0, 70.0, rows),
            "pressure": np.linspace(5.0, 6.0, rows),
            "level": np.linspace(0.1, 1.3, rows),
            "level2": np.linspace(1e4, 3e5, rows),
            "rise": np.linspace(0.1, 1.3, rows),
        },
        index=TICKS,
    )
    for (column, row), value in (changes or {}).items():
        frame[column] = frame[column].astype(object if isinstance(value, str) else float)
        frame.loc[TICKS[row], column] = value
    return frame


def _run(traced, frame, make=_plant, callbacks=(), on_error="record", **kwargs):
    plant = make()
    engine = gm.Engine([build() for build in callbacks], on_error=on_error)
    with graph.settings(traced=traced):
        results = engine.replay(plant, gm.Dataset.from_frame(frame), **kwargs)
    return engine, results, plant


def assert_same(frame, **kwargs):
    """Run traced and untraced, assert everything the engine reports is identical."""
    engine, traced, plant = _run(True, frame, **kwargs)
    _, plain, other = _run(False, frame, **kwargs)
    pd.testing.assert_frame_equal(traced.to_frame(), plain.to_frame(), check_exact=True)
    assert traced.to_frame().dtypes.tolist() == plain.to_frame().dtypes.tolist()
    assert traced.skip_counts == plain.skip_counts and traced.errors == plain.errors
    pd.testing.assert_frame_equal(
        pd.DataFrame(traced.summary()), pd.DataFrame(plain.summary()), check_exact=True
    )
    assert _persisted(plant) == _persisted(other)
    return engine, traced


def _persisted(plant):
    return {path: dict(module._input_values) for path, module in plant.named_modules()}


def test_a_replay_through_the_graph_equals_the_plain_path():
    """Units, volumetric flows, health, soft sensors and None outputs are exact."""
    engine, results = assert_same(_frame())
    assert set(engine.batch.claims) == {"first", "second"} and engine.batch.reasons == {}
    assert all(all(claims.claimed) for claims in engine.batch.claims.values())
    assert ("first", "health_score") in results.to_frame().columns


def test_the_setting_turns_the_batch_off():
    """Without the graph there is no batch."""
    engine, _, _ = _run(False, _frame())
    assert engine.batch is None


def test_missing_observations_are_skipped_not_claimed():
    """A missing value or a text flag skips the twin at its tick, as on the plain path."""
    engine, results = assert_same(_frame({("level", 3): np.nan, ("pressure", 5): "Alarm"}))
    assert sum(results.skip_counts["first"].values()) == 2
    assert not engine.batch.claims["first"].claimed[3] and engine.batch.claims["first"].claimed[4]


def test_rows_with_a_failing_check_run_on_the_plain_path_under_record():
    """The error is recorded with its tick, class and message; the other rows are claimed."""
    engine, results = assert_same(_frame({("level", 4): -1.0}))
    assert results.errors[0]["module"] == "first"
    assert results.errors[0]["type"] == "PhysicsRangeError"
    assert engine.batch.claims["first"].claimed.count(False) == 1


def test_rows_with_a_failing_check_raise_the_chained_step_error():
    """Under ``raise`` the plain path raises ``StepError`` with the same message and callbacks."""
    seen = []

    class Watch(Callback):
        def on_error(self, engine, error):
            seen.append((type(error).__name__, str(error), type(error.__cause__).__name__))

    frame = _frame({("level", 4): -1.0})
    for traced in (True, False):
        with pytest.raises(StepError) as raised:
            _run(traced, frame, callbacks=(Watch,), on_error="raise")
        assert isinstance(raised.value.__cause__, PhysicsRangeError)
    assert seen[0] == seen[1]


def test_non_finite_values_are_not_claimed():
    """A row whose output is infinite is left to the plain path and gives the same result."""
    engine, results = assert_same(_frame({("level", 2): 0.0}))
    assert not engine.batch.claims["first"].claimed[2]
    assert results["first"].inverse.tolist().count(float("inf")) == 1


def test_dated_parameters_apply_per_stretch_and_are_restored():
    """A design change inside the window splits the batch; the plan applies it again."""
    engine, results = assert_same(_frame(), make=_dated_plant)
    assert engine.batch.claims["first"].claimed.count(True) == len(TICKS)
    rise, level = results["first"].rise, np.linspace(0.1, 1.3, len(TICKS)) * 1e5
    assert rise.iloc[5] == pytest.approx(2.0 * level[5]) and rise.iloc[6] == pytest.approx(
        5.0 * level[6]
    )


def test_only_selects_twins():
    """``only`` limits the batch to the selected twins."""
    engine, results = assert_same(_frame(), only=["second"])
    assert set(engine.batch.claims) == {"second"}


def test_a_stateful_twin_runs_tick_by_tick_next_to_the_batch():
    """The stateful twin has no claims and a reason; its state is carried as before."""
    engine, results = assert_same(_frame(), make=lambda: _plant(with_tank=True))
    assert "stateful" in engine.batch.reasons["tank"] and "tank" not in engine.batch.claims
    assert set(engine.batch.claims) == {"first", "second"}


def test_event_log_events_are_identical_except_for_timing():
    """The observer hooks replay claimed rows in today's order with the same payloads."""
    logs = {}
    for traced in (True, False):
        log = EventLog()
        _run(traced, _frame({("level", 4): -1.0}), callbacks=(lambda log=log: log,))
        logs[traced] = [
            {k: v for k, v in event.items() if k not in {"ts", "duration_ms"}}
            for event in log.events
        ]
    assert logs[True] == logs[False] and any(e["kind"] == "forward" for e in logs[True])


def test_autocheckpoint_and_resume_equal_an_uninterrupted_run(tmp_path):
    """A run interrupted by a callback and resumed gives the uninterrupted frame."""

    class Interrupt(Callback):
        def on_step_end(self, engine, sample):
            if len(engine.results) == 6:
                raise KeyboardInterrupt

    path = tmp_path / "run.ckpt"
    _, whole, _ = _run(False, _frame())
    with pytest.raises(KeyboardInterrupt):
        _run(True, _frame(), callbacks=(lambda: AutoCheckpoint(path, every=4), Interrupt))
    resumed = gm.Engine.load_checkpoint(path).resume()
    pd.testing.assert_frame_equal(resumed.to_frame(), whole.to_frame(), check_exact=True)


def test_a_callback_that_raises_leaves_the_same_persisted_inputs():
    """The plant keeps the inputs of the last completed tick, interrupted or not."""

    class Stop(Callback):
        def on_step_end(self, engine, sample):
            if len(engine.results) == 5:
                raise RuntimeError("stop")

    persisted = []
    for traced in (True, False):
        plant = _plant()
        engine = gm.Engine([Stop()])
        with graph.settings(traced=traced), pytest.raises(RuntimeError):
            engine.replay(plant, gm.Dataset.from_frame(_frame()))
        persisted.append(_persisted(plant))
    assert persisted[0] == persisted[1] and persisted[0]["first"]["level"] == pytest.approx(
        (0.1 + 4 * 1.2 / 11) * 1e5
    )


def test_parameter_stretches_follow_the_dated_transitions():
    """Ticks share a stretch until the first tick at or after a later date."""
    from gemini.core.engine.step import BindingPlan

    plan = BindingPlan(_dated_plant(), gm.Dataset.from_frame(_frame()), "replay")
    assert plan.parameter_stretches(list(TICKS.to_pydatetime())) == [(0, 6), (6, 12)]
    assert plan.parameter_stretches([TICKS[0].to_pydatetime()]) == [(0, 1)]


class Duo(Module):
    """Two boosters in series: a composite twin with a formula output and an automatic sum."""

    def __init__(self):
        """Declare the children, the inlet, the outputs and the outlet."""
        super().__init__()

        # Modules
        self.front = Booster()
        self.back = Booster()

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.level = Control(float)

        # Outputs
        self.rise = Output.of(self.back.rise)
        self.power = Output(Electricity)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Both boosters get the duo's level."""

        # Modules
        first = self.front(inlet=inlets.inlet, level=self.level)
        second = self.back(inlet=first.outlets.outlet, level=self.level)

        # Outlets
        outlets = dict(outlet=second.outlets.outlet)
        return outlets


class Holder(Module):
    """A container whose child ``duo`` is a composite twin."""

    def __init__(self):
        """Declare the child."""
        super().__init__()

        # Modules
        self.duo = Duo()


def _holder(nested=False):
    plant = Holder()
    plant.bindings = {
        "duo": ModuleBindings(
            controls={"level": Binding(column="level", unit="bar")},
            inlets={"inlet": _inlet_bindings()},
        )
    }
    if nested:
        plant.bindings["duo.front"] = ModuleBindings(
            controls={"level": Binding(column="level", unit="bar")},
            inlets={"inlet": _inlet_bindings()},
            measured={"rise": Binding(column="rise", unit="bar")},
        )
    return plant


def test_a_composite_twin_is_one_traced_call():
    """The composite's formula output and automatic sum are exact; its children are not twins."""
    engine, results = assert_same(_frame({("level", 4): -1.0}), make=_holder)
    claims = engine.batch.claims["duo"]
    assert claims.claimed.count(False) == 1 and claims.graph.breaks == []
    assert results["duo"].rise.notna().sum() == len(TICKS) - 1


def test_a_twin_below_a_twin_disables_the_batch():
    """Child controls depend on the tick order of ``set_inputs``, so the run goes tick by tick."""
    engine, _ = assert_same(_frame(), make=lambda: _holder(nested=True))
    assert engine.batch.claims == {} and set(engine.batch.reasons) == {"duo", "duo.front"}
    assert "below another twin" in engine.batch.reasons["duo"]
