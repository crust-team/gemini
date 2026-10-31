"""The eager executor: arrays when it can, rows when it must, the numbers of the compiler."""

import numpy as np
import pytest

import gemini as gm
from gemini.compiler.executor import GraphExecutor
from gemini.engine.eager import EagerExecutor, _by_rows
from gemini.engine.executor import executor_for
from tests.fixtures.engine_plants import Booster, holder_plant, pair_frame, pair_plant
from tests.fixtures.parity import assert_frames_match


def _run(plant, frame, compile):
    """Replay ``frame`` on ``plant`` and return the engine."""
    engine = gm.Engine(plant, on_error="record", compile=compile)
    engine.replay(gm.Dataset.from_frame(frame))
    return engine


@pytest.mark.parametrize(
    "make",
    [pair_plant, lambda: pair_plant(with_tank=True), holder_plant],
    ids=["pair", "stateful", "composite"],
)
def test_eager_and_compiled_runs_give_the_same_numbers_and_errors(make):
    """Rows that fail, rows that work and a stateful twin agree between the executors."""
    frame = pair_frame({("level", 4): -1.0, ("level", 7): 0.0, ("flow", 9): np.nan})
    eager, compiled = (_run(make(), frame, compile) for compile in (False, True))
    assert isinstance(eager._executor, EagerExecutor)
    assert isinstance(compiled._executor, GraphExecutor)
    assert len(compiled.results.errors()) >= 2
    assert_frames_match(eager.results.to_frame(), compiled.results.to_frame())
    assert eager.results.failures == compiled.results.failures
    assert eager.module_states == compiled.module_states


def _streams():
    return {
        "fluid_in": gm.Stream(
            m_dot=np.full(3, 1.0), T=np.full(3, 300.0), p=np.full(3, 1e5), fluid=gm.WATER
        )
    }


def test_rows_that_all_work_are_one_array_call(monkeypatch):
    """No row is called for real when the array call works."""
    monkeypatch.setattr(EagerExecutor, "_rows", None)
    executor = EagerExecutor()
    prepared = executor.prepare(Booster(), _streams(), {"level": np.array([1.0, 2.0, 3.0])}, False)
    evaluation = executor.evaluate(prepared, 3, {})
    assert not evaluation.failed.any() and evaluation.breaks == []
    assert evaluation.result.outputs["rise"].tolist() == [2.0, 4.0, 6.0]
    assert evaluation.result.row(1).outputs.rise == 4.0


def test_an_array_call_that_raises_falls_back_to_the_rows():
    """A failing check stops the array call; the rows give each its own result or error."""
    module = Booster()
    streams = _streams()
    executor = EagerExecutor()
    prepared = executor.prepare(module, streams, {"level": np.array([1.0, -1.0, 2.0])}, False)
    evaluation = executor.evaluate(prepared, 3, {})
    assert evaluation.failed.tolist() == [False, True, False]
    assert "level = -1.0" in str(evaluation.error(1))
    assert evaluation.result.outputs["rise"][[0, 2]].tolist() == [1.0 * 2.0, 2.0 * 2.0]


def test_stateless_modules_are_called_once_on_arrays():
    """A stateless leaf takes the array path; state, hooks and the Python backend take rows."""
    module = Booster()
    assert not _by_rows(module)
    module.register_forward_pre_hook(lambda module, inlets: None)
    assert _by_rows(module)
    assert _by_rows(pair_plant(with_tank=True))
    with gm.runtime.settings(backend="python"):
        assert _by_rows(Booster())


def test_compile_false_or_no_compiler_runs_eager(monkeypatch):
    """Only a registered compiled executor is used, and only when asked for."""
    plant = pair_plant()
    assert isinstance(executor_for(plant, compile=True), GraphExecutor)
    assert isinstance(executor_for(plant, compile=False), EagerExecutor)
    monkeypatch.setattr("gemini.engine.executor._FACTORIES", {"eager": lambda plant: "eager"})
    assert executor_for(plant, compile=True) == "eager"


def test_the_compiler_returns_the_executor_of_a_plant():
    """``gm.compiler.compile`` shares the plant's graphs between executors."""
    plant = pair_plant()
    first, second = gm.compiler.compile(plant), gm.compiler.compile(plant)
    assert first.cache is second.cache
