"""The graph executor: ``compile`` gives a plant's executor and the engine runs through it."""

import numpy as np

import gemini as gm
from gemini.compiler.executor import GraphExecutor
from gemini.engine.executor import executor_for
from tests.fixtures.engine_plants import Booster


def test_compile_returns_an_executor_that_shares_the_graphs_of_the_plant():
    """Two executors of one plant use the one cache, so nothing is traced twice."""
    plant = Booster()
    first, second = gm.compiler.compile(plant), gm.compiler.compile(plant)
    assert isinstance(first, GraphExecutor) and first.cache is second.cache


def test_importing_the_compiler_registers_it_for_compiled_engines():
    """``compile=True`` finds the graph executor, ``compile=False`` does not."""
    plant = Booster()
    assert isinstance(executor_for(plant, compile=True), GraphExecutor)
    assert not isinstance(executor_for(plant, compile=False), GraphExecutor)


def test_an_executor_prepares_a_graph_and_evaluates_it_over_the_rows():
    """The evaluation holds the arrays of the rows and no break for a traceable leaf."""
    module = Booster()
    executor = gm.compiler.compile(module)
    streams = {
        "fluid_in": gm.Stream(
            m_dot=np.full(3, 1.0), T=np.full(3, 300.0), p=np.full(3, 1e5), fluid=gm.WATER
        )
    }
    prepared = executor.prepare(module, streams, {"level": np.array([1.0, 2.0, 3.0])}, False)
    evaluation = executor.evaluate(prepared, 3, {})
    assert evaluation.breaks == [] and not evaluation.failed.any()
    assert evaluation.result.outputs["rise"].tolist() == [2.0, 4.0, 6.0]
