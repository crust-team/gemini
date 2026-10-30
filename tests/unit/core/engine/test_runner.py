"""The runner: chunks of ticks through graphs, on either backend, with the callbacks replayed."""

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini import backends, ops
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
from tests.fixtures.engine_tank import ROW, TIME, tank

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


def _run(backend, frame, make=_plant, callbacks=(), on_error="record", **kwargs):
    plant = make()
    engine = gm.Engine([build() for build in callbacks], on_error=on_error)
    with backends.settings(backend=backend):
        results = engine.replay(plant, gm.Dataset.from_frame(frame), **kwargs)
    return engine, results, plant


def assert_same(frame, **kwargs):
    """Run on both backends and assert that everything the engine reports is identical."""
    engine, numpy, plant = _run("numpy", frame, **kwargs)
    _, python, other = _run("python", frame, **kwargs)
    pd.testing.assert_frame_equal(numpy.to_frame(), python.to_frame(), check_exact=True)
    assert numpy.to_frame().dtypes.tolist() == python.to_frame().dtypes.tolist()
    assert numpy.skip_counts == python.skip_counts and numpy.errors == python.errors
    pd.testing.assert_frame_equal(
        pd.DataFrame(numpy.summary()), pd.DataFrame(python.summary()), check_exact=True
    )
    assert _persisted(plant) == _persisted(other)
    return engine, numpy


def _persisted(plant):
    return {path: dict(module._input_values) for path, module in plant.named_modules()}


def test_a_replay_on_arrays_equals_the_replay_row_by_row():
    """Units, volumetric flows, health, soft sensors and None outputs are exact."""
    engine, results = assert_same(_frame())
    assert engine.graph_breaks == {"first": [], "second": []}
    assert ("first", "health_score") in results.to_frame().columns


def test_missing_observations_are_skipped():
    """A missing value or a text flag skips the twin at its tick."""
    _, results = assert_same(_frame({("level", 3): np.nan, ("pressure", 5): "Alarm"}))
    assert sum(results.skip_counts["first"].values()) == 2
    assert results["first"].rise.isna().tolist()[3:6] == [True, False, True]


def test_rows_with_a_failing_check_are_recorded_with_their_tick_class_and_message():
    """The other rows of the chunk keep their results."""
    _, results = assert_same(_frame({("level", 4): -1.0}))
    assert results.errors[0]["module"] == "first"
    assert results.errors[0]["type"] == "PhysicsRangeError"
    assert results["first"].rise.notna().sum() == len(TICKS) - 1


def test_rows_with_a_failing_check_raise_the_step_error_after_the_earlier_rows():
    """Under ``raise`` the error is a ``StepError`` chained to the check's error."""
    seen = []

    class Watch(Callback):
        def on_error(self, engine, error):
            seen.append((type(error).__name__, str(error), type(error.__cause__).__name__))

    frame = _frame({("level", 4): -1.0})
    for backend in ("numpy", "python"):
        engine = gm.Engine([Watch()], on_error="raise")
        with backends.settings(backend=backend), pytest.raises(StepError) as raised:
            engine.replay(_plant(), gm.Dataset.from_frame(frame))
        assert isinstance(raised.value.__cause__, PhysicsRangeError)
        assert len(engine.results) == 4 and engine.position == TICKS[3]
    assert seen[0] == seen[1]


def test_non_finite_values_are_results():
    """A row whose output is infinite is a result, the same on both backends."""
    _, results = assert_same(_frame({("level", 2): 0.0}))
    assert results["first"].inverse.tolist().count(float("inf")) == 1


def test_dated_parameters_apply_per_stretch():
    """A design change inside the window splits the chunks; each applies its own snapshot."""
    _, results = assert_same(_frame(), make=_dated_plant)
    rise, level = results["first"].rise, np.linspace(0.1, 1.3, len(TICKS)) * 1e5
    assert rise.iloc[5] == pytest.approx(2.0 * level[5]) and rise.iloc[6] == pytest.approx(
        5.0 * level[6]
    )


def test_only_selects_twins():
    """``only`` limits the run to the selected twins."""
    _, results = assert_same(_frame(), only=["second"])
    assert "first" not in results.to_frame().columns.get_level_values(0)


def test_a_stateful_twin_is_a_root_break_stepped_next_to_the_traced_twins():
    """The stateful twin has a reason in ``graph_breaks``; its state is carried as before."""
    engine, results = assert_same(_frame(), make=lambda: _plant(with_tank=True))
    assert "stateful" in engine.graph_breaks["tank"][0] and engine.graph_breaks["first"] == []
    assert engine.module_states["tank"]["total"] == pytest.approx(results["tank"].content.iloc[-1])


def test_event_log_events_are_identical_on_both_backends_except_for_timing():
    """Every module call of every tick is logged in the same order with the same payloads."""
    logs = {}
    for backend in ("numpy", "python"):
        log = EventLog()
        _run(backend, _frame({("level", 4): -1.0}), callbacks=(lambda log=log: log,))
        logs[backend] = [{k: v for k, v in event.items() if k != "ts"} for event in log.events]
    assert logs["numpy"] == logs["python"] and any(e["kind"] == "forward" for e in logs["numpy"])


def test_autocheckpoint_and_resume_equal_an_uninterrupted_run(tmp_path):
    """A run interrupted by a callback and resumed gives the uninterrupted frame."""

    class Interrupt(Callback):
        def on_step_end(self, engine, sample):
            if len(engine.results) == 6:
                raise KeyboardInterrupt

    path = tmp_path / "run.ckpt"
    _, whole, _ = _run("python", _frame())
    with pytest.raises(KeyboardInterrupt):
        _run("numpy", _frame(), callbacks=(lambda: AutoCheckpoint(path, every=4), Interrupt))
    resumed = gm.Engine.load_checkpoint(path).resume()
    pd.testing.assert_frame_equal(resumed.to_frame(), whole.to_frame(), check_exact=True)


def test_a_callback_that_raises_leaves_the_inputs_of_its_tick_persisted():
    """The plant keeps the inputs of the tick the callback stopped at, on either backend."""

    class Stop(Callback):
        def on_step_end(self, engine, sample):
            if len(engine.results) == 5:
                raise RuntimeError("stop")

    persisted = []
    for backend in ("numpy", "python"):
        plant = _plant()
        engine = gm.Engine([Stop()])
        with backends.settings(backend=backend), pytest.raises(RuntimeError):
            engine.replay(plant, gm.Dataset.from_frame(_frame()))
        persisted.append(_persisted(plant))
    assert persisted[0] == persisted[1] and persisted[0]["first"]["level"] == pytest.approx(
        (0.1 + 4 * 1.2 / 11) * 1e5
    )


def test_a_callback_that_changes_the_run_is_called_before_each_tick_is_evaluated():
    """With ``changes_run`` the gain set at the start of tick 3 applies from tick 3."""

    class Retune(Callback):
        changes_run = True

        def on_step_start(self, engine, sample):
            if len(engine.results) == 3:
                engine.plant.first.update_params(gain=7.0)

    _, results, _ = _run("numpy", _frame(), callbacks=(Retune,))
    level = np.linspace(0.1, 1.3, len(TICKS)) * 1e5
    assert results["first"].rise.iloc[2] == pytest.approx(2.0 * level[2])
    assert results["first"].rise.iloc[3] == pytest.approx(7.0 * level[3])


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
    assert engine.graph_breaks == {"duo": []}
    assert results["duo"].rise.notna().sum() == len(TICKS) - 1


def test_a_twin_below_a_twin_reads_what_the_twin_persisted_tick_by_tick():
    """Child controls depend on the tick order of ``set_inputs``: one tick per chunk."""
    engine, _ = assert_same(_frame(), make=lambda: _holder(nested=True))
    assert set(engine.graph_breaks) == {"duo", "duo.front"}


def _tank_run(rows, on_error="record"):
    """Replay the shared tank over rows given as column values."""
    module = tank()
    frame = pd.DataFrame(rows, index=pd.date_range(TIME, periods=len(rows["rate"]), freq="15min"))
    engine = gm.Engine(on_error=on_error)
    return engine, engine.replay(module, gm.Dataset.from_frame(frame))


def test_missing_data_is_a_counted_skip_and_failures_are_recorded_or_raised():
    """Skips are counted per twin; failures are recorded, or raised as StepError."""
    rows = {name: [value] * 3 for name, value in ROW.items()}
    rows["p"][1], rows["rate"][2] = np.nan, -1.0
    _, results = _tank_run(rows)
    assert results.skip_counts == {"": {"p": 1}}
    assert (
        results.errors[0]["message"] == "negative flow"
        and results.errors[0]["type"] == "ValueError"
    )
    assert results[""].flow.tolist()[0] == 2.0
    with pytest.raises(StepError, match="negative flow") as raised:
        _tank_run(rows, on_error="raise")
    assert isinstance(raised.value.__cause__, ValueError)


def test_a_simulation_skips_the_plant_when_data_is_missing():
    """Simulation counts missing data as a skip of the plant, as replay does for twins."""
    module = tank()
    frame = pd.DataFrame(
        {name: [value] * 2 for name, value in ROW.items()},
        index=pd.date_range(TIME, periods=2, freq="15min"),
    )
    frame.loc[frame.index[1], "rate"] = np.nan
    data = gm.Dataset.from_frame(frame)
    results = gm.Engine().simulate(module, data, gm.Clock.from_data(data))
    assert results.skip_counts == {"": {"rate": 1}} and results[""].flow.dropna().tolist() == [2.0]
