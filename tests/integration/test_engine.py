"""Engine parity, state, callbacks, energy and restart guarantees."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.core.engine import checkpoint
from gemini.core.engine.callbacks import AutoCheckpoint, Callback, EventLog
from gemini.core.engine.results import Results
from gemini.core.types import Control, Output
from gemini.core.types.bindings import Binding, DatedParams, ModuleBindings

ROOT = Path(__file__).parents[2]
REFERENCE = ROOT / "tests/fixtures/engine_reference"


class Accumulator(gm.modules.Module):
    """Simple importable test integrator with a JSON state."""

    stateful = True

    def __init__(self):
        """Declare the accumulator's test state and ports."""
        super().__init__()

        # Controls
        self.rate = Control(float)

        # Outputs
        self.value = Output(float)

    def initial_state(self):
        """Start at zero."""
        return {"value": 0.0}

    def forward(self, inlets):
        """Expose a stateless rate observation."""

        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.value = self.rate

    def step(self, state, dt, inlets):
        """Integrate with explicit state."""

        # Outputs
        state = {"value": state["value"] + self.rate * dt}
        result = self(inlets, rate=state["value"])

        return state, result


@pytest.fixture
def setup(fresh_plant, reference_dataset):
    """Create a fresh plant and first-day measurements."""
    return fresh_plant, reference_dataset


def test_reference_replay_and_simulate(setup):
    """Preserve every pre-refactor output, including health fields and scenario diagnostics.

    NOTE(refactor): pandas' ordinary decimal parser changes a few chained scenario values at
    ~1e-15 relative to the old raw-unit CSV conversion path, hence the simulate tolerance.
    """
    plant, data = setup
    old = pd.read_pickle(REFERENCE / "replay.pkl")
    old = old.rename(columns={"filter_hot": "filters.hot", "filter_return": "filters.cold"})
    actual = gm.Engine(on_error="raise").replay(plant, data).to_frame()
    pd.testing.assert_frame_equal(actual[old.columns], old, check_names=False)
    clock = gm.Clock.days(2024, 6, 7)
    raw = data.read(data.start, data.start)
    assumed = pd.DataFrame([raw.iloc[0].to_dict()] * 24, index=list(clock))
    result = gm.Engine(on_error="raise").simulate(plant, gm.Dataset.from_frame(assumed), clock)
    old = pd.read_pickle(REFERENCE / "simulate.pkl")
    old = old.rename(columns={"filter_hot": "filters.hot", "filter_return": "filters.cold"})
    actual = result.to_frame()
    pd.testing.assert_frame_equal(
        actual[old.columns].reset_index(drop=True),
        old.reset_index(drop=True),
        check_exact=False,
        rtol=1e-14,
        atol=0,
    )
    assert len(result) == 24
    for path, field in result._energy:
        total = (actual[path, field] * 3600).sum()
        assert result.summary().loc[(path, field), "energy_J"] == pytest.approx(total)


def test_replay_can_skip_outputs(setup):
    """A no-output replay retains fluid execution without running diagnostics on empty values."""
    plant, data = setup
    first = data.window(end=data.start)
    with gm.no_outputs():
        result = gm.Engine(on_error="raise").replay(plant, first)
    assert len(result) == 1
    fields = set(result.to_frame().columns.get_level_values("field"))
    assert "operating" in fields
    assert "power" not in fields


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_replay_of_example_data_skips_nothing_at_any_timestamp_resolution(
    fresh_plant, fast_frame, unit
):
    """Every twin runs on every tick of one example day, whatever the parsed time resolution.

    pandas 3 parses the example CSV times as microseconds; comparing them with nanosecond
    ``Timestamp.value`` once made every tick a gap, so replay silently skipped every twin.
    """
    frame = fast_frame.iloc[:96].copy()
    frame["time"] = frame["time"].dt.as_unit(unit)
    data = gm.Dataset.from_frame(frame, time_column="time")
    result = gm.Engine(on_error="raise").replay(fresh_plant, data)
    assert len(result) == 96
    assert result.skip_counts == {}
    assert result["doublet.esp"].head.notna().all()


class Interrupted(BaseException):
    """Model a scheduler cancellation without ordinary-error recovery."""


class StopAndSave(Callback):
    """Interrupt after a committed step and save from the error hook."""

    def __init__(self, path, count):
        """Remember the checkpoint destination and stop position."""
        self.path, self.count = path, count

    def on_step_end(self, engine, sample):
        """Cancel only once the requested result row exists."""
        if len(engine.results) == self.count:
            raise Interrupted("stop")

    def on_error(self, engine, error):
        """Save the completed boundary after cancellation."""
        engine.save_checkpoint(self.path)


@pytest.mark.parametrize("kind", ["replay", "simulate"])
def test_interrupt_resume(setup, tmp_path, kind):
    """Fresh-engine resume reproduces uninterrupted results and integration exactly."""
    plant, data = setup
    data = data.window(end=data.start + pd.Timedelta(hours=2, minutes=45))
    clock = gm.Clock.from_data(data)
    args = [plant, data] + ([clock] if kind == "simulate" else [])
    expected = getattr(gm.Engine(on_error="raise"), kind)(*args)
    path = tmp_path / "run.ckpt"
    engine = gm.Engine([StopAndSave(path, 5)], on_error="raise")
    with pytest.raises(Interrupted):
        getattr(engine, kind)(*args)
    checkpoint = json.loads(path.read_text())
    assert checkpoint["position"] == list(clock)[4].isoformat().replace("+00:00", "Z")
    loaded = gm.Engine.load_checkpoint(path)
    assert loaded.plant.state_dict() == plant.state_dict()
    actual = loaded.resume()
    pd.testing.assert_frame_equal(actual.to_frame(), expected.to_frame(), check_exact=True)
    pd.testing.assert_frame_equal(actual.summary(), expected.summary(), check_exact=True)
    assert loaded.resume() is actual


def test_live_idempotency(tmp_path):
    """New engine calls process only newly available timestamps; repeated now returns no rows."""
    plant = Accumulator()
    plant.bindings = {"": ModuleBindings(controls={"rate": Binding(column="rate", unit="-")})}
    frame = pd.DataFrame(
        {"rate": [1.0, 1.0]},
        index=pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC"),
    )
    data = gm.Dataset.from_frame(frame)
    path = tmp_path / "live.ckpt"
    first_now = data.start
    second_now = data.start + pd.Timedelta(minutes=15)
    out = gm.Engine().live(plant, data, path, now=first_now)
    assert len(out) == 1
    second = gm.Engine().live(plant, data, path, now=second_now)
    assert len(second) == 1
    assert not set(out.to_frame().index) & set(second.to_frame().index)
    engine = gm.Engine()
    assert len(engine.live(plant, data, path, now=second_now)) == 0
    assert len(engine.results) == 2
    assert len(gm.Engine.load_checkpoint(path).resume()) == 2


def test_missing_data_dates_events_and_export(setup, tmp_path):
    """Missing observations skip only their twin; dated snapshots and event hooks remain active."""
    plant, data = setup
    frame = data.read(data.start, data.end).iloc[:12]
    frame.loc[frame.index[0], "doublet.esp.suction.p"] = np.nan
    module = plant.filters.hot
    module.param_history.append(
        DatedParams(valid_from=frame.index[1], params=module.params_at(None) | {"dp_nominal": 3200})
    )
    events = EventLog(tmp_path / "events.jsonl")
    result = gm.Engine([events], on_error="raise").replay(plant, gm.Dataset.from_frame(frame))
    assert result["doublet.esp"].head.notna().sum() == 11
    assert (
        result["filters.hot"].pressure_drop.iloc[1]
        > 1.99 * result["filters.hot"].pressure_drop.iloc[0]
    )
    assert result.skip_counts == {"doublet.esp": {"doublet.esp.suction.p": 1}}
    assert not any(m._hooks for m in plant.modules())
    assert (
        json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])["kind"] == "run_start"
    )
    for extension in ("csv", "parquet"):
        path = result.save(tmp_path / ("results." + extension))
        loaded = Results.load(path)
        pd.testing.assert_frame_equal(loaded.to_frame(), result.to_frame())
        pd.testing.assert_frame_equal(loaded.summary(), result.summary())


def test_autocheckpoint_and_callback_order(setup, tmp_path):
    """Callbacks observe committed positions; automatic snapshots resume only unfinished rows."""
    plant, data = setup
    calls = []

    class Observe(Callback):
        """Record lifecycle events."""

        def on_run_start(self, engine):
            """Observe run start."""
            calls.append("start")

        def on_step_start(self, engine, sample):
            """Observe step start."""
            calls.append("before")

        def on_step_end(self, engine, sample):
            """Observe committed position."""
            assert engine.position == sample.t
            calls.append("after")

        def on_run_end(self, engine):
            """Observe run end."""
            calls.append("end")

    path = tmp_path / "automatic.ckpt"
    engine = gm.Engine([Observe(), AutoCheckpoint(path, every="1h")])
    actual = engine.replay(plant, data.window(end="2024-06-07T01:00:00Z"))
    assert calls == ["start"] + ["before", "after"] * 5 + ["end"]
    loaded = gm.Engine.load_checkpoint(path)
    assert len(loaded.results) == 4
    pd.testing.assert_frame_equal(loaded.resume().to_frame(), actual.to_frame())


def test_error_policies_and_missing_columns(setup):
    """Invalid physics records module-specific errors or raises; absent columns fail together."""
    plant, data = setup
    frame = data.read(data.start, data.end).iloc[:2]
    frame.loc[frame.index[0], "doublet.esp.suction.p"] = -100
    result = gm.Engine().replay(plant, gm.Dataset.from_frame(frame))
    assert result.errors[0]["module"] == "doublet.esp"
    assert result["filters.hot"].pressure_drop.notna().all()
    with pytest.raises(gm.errors.StepError, match="doublet.esp"):
        gm.Engine(on_error="raise").replay(plant, gm.Dataset.from_frame(frame))
    with pytest.raises(
        gm.errors.BindingError, match="suction.p, doublet.reservoir.production_rate"
    ):
        gm.Engine().replay(
            plant,
            gm.Dataset.from_frame(
                frame.drop(columns=["doublet.esp.suction.p", "doublet.reservoir.production_rate"])
            ),
        )


def test_plant_only_checkpoint(setup, tmp_path):
    """A configured engine can save before its first run, including fitted design overrides."""
    plant, _ = setup
    plant.heat_exchanger.update_params(ua=123456)
    engine = gm.Engine()
    engine.plant = plant
    path = tmp_path / "design.ckpt"
    engine.save_checkpoint(path)
    other = gm.Engine.load_checkpoint(path)
    assert other.plant.state_dict() == plant.state_dict()
    assert other.plant.bindings == plant.bindings
    assert len(other.resume()) == 0


def test_stateful_measured_and_integrated(tmp_path):
    """Measured state resets each tick; unbound state integrates and survives checkpoints."""
    plant = Accumulator()
    plant.bindings = {"": ModuleBindings(controls={"rate": Binding(column="rate", unit="-")})}
    frame = pd.DataFrame(
        {"rate": [1, 1, 1], "observed": [10, 20, 30]},
        index=pd.date_range("2024-01-01", periods=3, freq="1s", tz="UTC"),
    )
    data = gm.Dataset.from_frame(frame)
    engine = gm.Engine(on_error="raise")
    assert engine.replay(plant, data)[""].value.tolist() == [1, 2, 3]
    path = tmp_path / "state.ckpt"
    with pytest.raises(Interrupted):
        gm.Engine([StopAndSave(path, 1)]).replay(plant, data)
    assert gm.Engine.load_checkpoint(path).resume()[""].value.tolist() == [1, 2, 3]
    plant.bindings[""].state = {"value": Binding(column="observed", unit="-")}
    assert engine.replay(plant, data)[""].value.tolist() == [11, 21, 31]
    assert engine.module_states[""] == {"value": 30}


def test_empty_live_and_fallback_storage(setup, tmp_path, monkeypatch):
    """An empty live window is resumable and CSV fallback retains exact cells."""
    plant, data = setup
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    path = tmp_path / "empty.ckpt"
    assert len(gm.Engine().live(plant, data, path, now="2024-01-01")) == 0
    assert len(gm.Engine.load_checkpoint(path).resume()) == 0
    engine = gm.Engine()
    expected = engine.replay(plant, data.window(end=data.start))
    path = tmp_path / "fallback.ckpt"
    engine.save_checkpoint(path)
    assert json.loads(path.read_text())["results_file"].endswith(".csv")
    pd.testing.assert_frame_equal(
        gm.Engine.load_checkpoint(path).resume().to_frame(), expected.to_frame()
    )


def test_failed_checkpoint_publication_keeps_previous(setup, tmp_path, monkeypatch):
    """Failure before the manifest rename leaves a fully readable previous generation."""
    plant, data = setup
    engine = gm.Engine()
    engine.replay(plant, data.window(end=data.start))
    path = tmp_path / "atomic.ckpt"
    engine.save_checkpoint(path)
    previous = path.read_bytes()

    def fail(source, destination):
        """Model a filesystem failure during atomic publication."""
        raise OSError("simulated rename failure")

    monkeypatch.setattr(checkpoint.os, "replace", fail)
    engine.replay(plant, data)
    with pytest.raises(OSError, match="rename"):
        engine.save_checkpoint(path)
    assert path.read_bytes() == previous
    assert len(gm.Engine.load_checkpoint(path).resume()) == 1


def accumulator(frame):
    """Return an accumulator bound to a ``rate`` column and the matching dataset."""
    plant = Accumulator()
    plant.bindings = {"": ModuleBindings(controls={"rate": Binding(column="rate", unit="-")})}
    return plant, gm.Dataset.from_frame(frame)


@pytest.mark.parametrize("count", [10, 13])
def test_resume_keeps_held_rows_when_the_clock_is_finer_than_the_data(tmp_path, count):
    """Bug E-engine-001: resume lost the held row, or refused to resume after the last row."""
    index = pd.date_range("2024-01-01", periods=4, freq="1h", tz="UTC")
    plant, data = accumulator(pd.DataFrame({"rate": [1.0, 2.0, 3.0, 4.0]}, index=index))
    clock = gm.Clock.range("2024-01-01T00:00Z", "2024-01-01T04:00Z", "15min")
    expected = gm.Engine(on_error="raise").simulate(plant, data, clock)
    path = tmp_path / "run.ckpt"
    with pytest.raises(Interrupted):
        gm.Engine([StopAndSave(path, count)], on_error="raise").simulate(plant, data, clock)
    actual = gm.Engine.load_checkpoint(path).resume()
    pd.testing.assert_frame_equal(actual.to_frame(), expected.to_frame(), check_exact=True)


def test_live_step_grid_stays_anchored_between_calls(tmp_path):
    """Bug E-engine-006: a later call with off-grid rows kept the first call's 15-minute grid."""
    path = tmp_path / "live.ckpt"
    first = pd.DataFrame(
        {"rate": [1.0, 1.0]},
        index=pd.DatetimeIndex(["2024-01-01 00:00", "2024-01-01 00:15"], tz="UTC"),
    )
    plant, data = accumulator(first)
    gm.Engine().live(plant, data, path, step="15min", now="2024-01-01T00:15Z")
    second = pd.DataFrame(
        {"rate": [2.0, 2.0]},
        index=pd.DatetimeIndex(["2024-01-01 00:22", "2024-01-01 00:37"], tz="UTC"),
    )
    fresh = gm.Engine().live(
        plant, gm.Dataset.from_frame(second), path, step="15min", now="2024-01-01T01:00Z"
    )
    assert [t.strftime("%H:%M") for t in fresh.to_frame().index] == ["00:30"]


def test_live_single_row_call_reuses_the_checkpointed_step(tmp_path):
    """Bug E-engine-007: one new row per live call was integrated over one hour, not 15 minutes."""
    path = tmp_path / "live.ckpt"
    index = pd.date_range("2024-01-01", periods=3, freq="15min", tz="UTC")
    plant, data = accumulator(pd.DataFrame({"rate": [1.0, 1.0, 1.0]}, index=index))
    gm.Engine().live(plant, data.window(end=index[1]), path, now=index[1])
    fresh = gm.Engine().live(plant, data.window(start=index[2]), path, now=index[2])
    assert fresh[""].value.tolist() == [2700.0]


def test_live_keeps_the_callers_error_policy_and_plant(tmp_path):
    """Bug E-engine-008: restoring a live checkpoint replaced on_error and the supplied plant."""
    path = tmp_path / "live.ckpt"
    index = pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC")
    plant, data = accumulator(pd.DataFrame({"rate": [1.0, 1.0]}, index=index))
    gm.Engine().live(plant, data, path, now=index[0])
    engine = gm.Engine(on_error="raise")
    engine.live(plant, data, path, now=index[1])
    assert engine.on_error == "raise"
    assert engine.plant is plant
    with pytest.raises(gm.errors.CheckpointError, match="plant_class = .*Accumulator"):
        gm.Engine().live(NotANumber(), data, path, now=index[1])


class NotANumber(gm.modules.Module):
    """Leaf whose output is always NaN."""

    def __init__(self):
        """Declare one control and one output."""
        super().__init__()

        # Controls
        self.rate = Control(float)

        # Outputs
        self.value = Output(float)

    def forward(self, inlets):
        """Expose no fluid outlets."""

        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.value = float("nan")


class Boom(Callback):
    """Fail after the first committed step."""

    def on_step_end(self, engine, sample):
        """Raise an ordinary error from a callback."""
        raise ValueError("boom")


def test_event_log_never_changes_results_and_always_detaches(tmp_path):
    """Bugs E-engine-004/005: NaN outputs became errors; an aborted run left hooks attached."""
    plant = NotANumber()
    plant.bindings = {"": ModuleBindings(controls={"rate": Binding(column="rate", unit="-")})}
    index = pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC")
    data = gm.Dataset.from_frame(pd.DataFrame({"rate": [1.0, 1.0]}, index=index))
    for events in (EventLog(), EventLog(tmp_path / "events.jsonl")):
        result = gm.Engine([events]).replay(plant, data)
        assert result.errors == []
        assert result[""].value.isna().all()
    assert "NaN" in (tmp_path / "events.jsonl").read_text()
    with pytest.raises(ValueError, match="boom"):
        gm.Engine([EventLog(), Boom()]).replay(plant, data)
    assert not plant._hooks and not plant._pre_hooks
