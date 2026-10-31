"""The runner: chunks of ticks through graphs, on either backend, with the callbacks replayed."""

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.engine.callbacks import AutoCheckpoint, Callback, EventLog
from gemini.errors import PhysicsError, RunError
from tests.fixtures.engine_plants import (
    TICKS,
    dated_pair_plant,
    holder_plant,
    pair_frame,
    pair_plant,
)
from tests.fixtures.engine_tank import ROW, TIME, tank
from tests.fixtures.errors import raises


def _run(backend, frame, make=pair_plant, callbacks=(), on_error="record", **kwargs):
    plant = make()
    engine = gm.Engine(plant, backend, [build() for build in callbacks], on_error)
    results = engine.replay(gm.Dataset.from_frame(frame), **kwargs)
    return engine, results, plant


def assert_same(frame, **kwargs):
    """Run on both backends and assert that everything the engine reports is identical."""
    engine, numpy, plant = _run("numpy", frame, **kwargs)
    _, python, other = _run("python", frame, **kwargs)
    pd.testing.assert_frame_equal(numpy.to_frame(), python.to_frame(), check_exact=True)
    assert numpy.to_frame().dtypes.tolist() == python.to_frame().dtypes.tolist()
    assert numpy.skip_counts == python.skip_counts and numpy.errors() == python.errors()
    pd.testing.assert_frame_equal(
        numpy.to_frame(table="energy"), python.to_frame(table="energy"), check_exact=True
    )
    assert _persisted(plant) == _persisted(other)
    return engine, numpy


def _persisted(plant):
    return {path: dict(module._input_values) for path, module in plant.named_modules()}


def test_a_replay_on_arrays_equals_the_replay_row_by_row():
    """Units, volumetric flows, health, soft sensors and None outputs are exact."""
    engine, results = assert_same(pair_frame())
    assert engine.graph_breaks == {"first": [], "second": []}
    assert "first.health_score" in results.to_frame().columns


def test_missing_observations_are_skipped():
    """A missing value or a text flag skips the twin at its tick."""
    _, results = assert_same(pair_frame({("level", 3): np.nan, ("pressure", 5): "Alarm"}))
    assert sum(results.skip_counts["first"].values()) == 2
    assert results["first"].rise.isna().tolist()[3:6] == [True, False, True]


def test_rows_with_a_failing_check_are_recorded_with_their_tick_code_and_message():
    """The other rows of the chunk keep their results."""
    _, results = assert_same(pair_frame({("level", 4): -1.0}))
    assert results.errors()[0]["path"] == "first"
    assert results.errors()[0]["code"] == "out_of_range"
    assert results["first"].rise.notna().sum() == len(TICKS) - 1


def test_rows_with_a_failing_check_raise_the_step_error_after_the_earlier_rows():
    """Under ``raise`` the error is a ``RunError`` chained to the check's error."""
    seen = []

    class Watch(Callback):
        def on_error(self, engine, error):
            seen.append((type(error).__name__, str(error), type(error.__cause__).__name__))

    frame = pair_frame({("level", 4): -1.0})
    for backend in ("numpy", "python"):
        engine = gm.Engine(pair_plant(), backend, [Watch()], "raise")
        with raises(RunError, "step") as raised:
            engine.replay(gm.Dataset.from_frame(frame))
        assert isinstance(raised.value.__cause__, PhysicsError)
        assert len(engine.results) == 4 and engine.position == TICKS[3]
    assert seen[0] == seen[1]


def test_non_finite_values_are_results():
    """A row whose output is infinite is a result, the same on both backends."""
    _, results = assert_same(pair_frame({("level", 2): 0.0}))
    assert results["first"].inverse.tolist().count(float("inf")) == 1


def test_dated_parameters_apply_per_stretch():
    """A design change inside the window splits the chunks; each applies its own snapshot."""
    _, results = assert_same(pair_frame(), make=dated_pair_plant)
    rise, level = results["first"].rise, np.linspace(0.1, 1.3, len(TICKS)) * 1e5
    assert rise.iloc[5] == pytest.approx(2.0 * level[5]) and rise.iloc[6] == pytest.approx(
        5.0 * level[6]
    )


def test_only_selects_twins():
    """``only`` limits the run to the selected twins."""
    _, results = assert_same(pair_frame(), only=["second"])
    assert "first" not in results.to_frame().columns.get_level_values(0)


def test_a_stateful_twin_is_a_root_break_stepped_next_to_the_traced_twins():
    """The stateful twin has a reason in ``graph_breaks``; its state is carried as before."""
    engine, results = assert_same(pair_frame(), make=lambda: pair_plant(with_tank=True))
    assert "stateful" in engine.graph_breaks["tank"][0] and engine.graph_breaks["first"] == []
    assert engine.module_states["tank"]["total"] == pytest.approx(results["tank"].content.iloc[-1])


def test_event_log_events_are_identical_on_both_backends_except_for_timing():
    """Every module call of every tick is logged in the same order with the same payloads."""
    logs = {}
    for backend in ("numpy", "python"):
        log = EventLog()
        _run(backend, pair_frame({("level", 4): -1.0}), callbacks=(lambda log=log: log,))
        logs[backend] = [{k: v for k, v in event.items() if k != "ts"} for event in log.events]
    assert logs["numpy"] == logs["python"] and any(e["kind"] == "forward" for e in logs["numpy"])


def test_autocheckpoint_and_resume_equal_an_uninterrupted_run(tmp_path):
    """A run interrupted by a callback and resumed gives the uninterrupted frame."""

    class Interrupt(Callback):
        def on_step_end(self, engine, sample):
            if len(engine.results) == 6:
                raise KeyboardInterrupt

    path = tmp_path / "run.ckpt"
    _, whole, _ = _run("python", pair_frame())
    with pytest.raises(KeyboardInterrupt):
        _run("numpy", pair_frame(), callbacks=(lambda: AutoCheckpoint(path, every=4), Interrupt))
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
        plant = pair_plant()
        engine = gm.Engine(plant, backend, [Stop()])
        with pytest.raises(RuntimeError):
            engine.replay(gm.Dataset.from_frame(pair_frame()))
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
                engine.plant.first.set_params("", {"gain": 7.0})

    _, results, _ = _run("numpy", pair_frame(), callbacks=(Retune,))
    level = np.linspace(0.1, 1.3, len(TICKS)) * 1e5
    assert results["first"].rise.iloc[2] == pytest.approx(2.0 * level[2])
    assert results["first"].rise.iloc[3] == pytest.approx(7.0 * level[3])


def test_a_composite_twin_is_one_traced_call():
    """The composite's formula output and automatic sum are exact; its children are not twins."""
    engine, results = assert_same(pair_frame({("level", 4): -1.0}), make=holder_plant)
    assert engine.graph_breaks == {"duo": []}
    assert results["duo"].rise.notna().sum() == len(TICKS) - 1


def test_a_twin_below_a_twin_reads_what_the_twin_persisted_tick_by_tick():
    """Child controls depend on the tick order of ``set_inputs``: one tick per chunk."""
    engine, _ = assert_same(pair_frame(), make=lambda: holder_plant(nested=True))
    assert set(engine.graph_breaks) == {"duo", "duo.front"}


def _tank_run(rows, on_error="record"):
    """Replay the shared tank over rows given as column values."""
    module = tank()
    frame = pd.DataFrame(rows, index=pd.date_range(TIME, periods=len(rows["rate"]), freq="15min"))
    engine = gm.Engine(module, on_error=on_error)
    return engine, engine.replay(gm.Dataset.from_frame(frame))


def test_missing_data_is_a_counted_skip_and_failures_are_recorded_or_raised():
    """Skips are counted per twin; failures are recorded, or raised as RunError."""
    rows = {name: [value] * 3 for name, value in ROW.items()}
    rows["p"][1], rows["rate"][2] = np.nan, -1.0
    _, results = _tank_run(rows)
    assert results.skip_counts == {"": {"p": 1}}
    errors = results.errors()
    assert [row["code"] for row in errors] == ["missing_value", "module_error"]
    assert errors[1]["message"] == "negative flow"
    assert results[""].flow.tolist()[0] == 2.0
    with raises(RunError, "step", match="negative flow") as raised:
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
    results = gm.Engine(module).simulate(data, gm.engine.Clock.from_data(data))
    assert results.skip_counts == {"": {"rate": 1}} and results[""].flow.dropna().tolist() == [2.0]
