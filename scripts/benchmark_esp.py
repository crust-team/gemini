"""Benchmark the ESP and the full doublet_heat replay over the July dataset.

Run ``PYTHONPATH=. python scripts/benchmark_esp.py`` from the repository root. On the committed
2,976-row July 2024 dataset it evaluates the ESP of the shared doublet plant once per row (the
untraced path) and as one traced graph on the NumPy backend, with and without
common-subexpression elimination, then replays the whole plant through the graph and with
``gemini.graph.settings(traced=False)``. It checks that the results agree and prints the best of
``--repeat`` timings and the speedups. It is a benchmark, not a test.
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant
from gemini import graph
from gemini.core.types.flows import Stream
from gemini.graph import GraphCache, run

ROOT = Path(__file__).resolve().parents[1]

DATASET = ROOT / "examples/shared/doublet_heat/doublet_2024_15min_month.csv"
PLANT = ROOT / "examples/shared/doublet_heat/plant.json"
COLUMNS = ["suction.m_dot", "suction.T", "suction.p", "frequency"]
RTOL = 1e-12


def load():
    """Return the plant's ESP and its SI inputs: mass flow, T, p and frequency per row."""
    esp = DoubletHeatPlant.load(PLANT).doublet.esp
    frame = pd.read_csv(DATASET, parse_dates=["time"])
    rows = frame[[f"doublet.esp.{column}" for column in COLUMNS]].dropna().to_numpy()
    rows[:, 0] *= esp.fluid.properties(None, None).density
    return esp, rows


def untraced(esp, rows):
    """Call the ESP once per row and return the results."""
    return [
        esp(
            suction=gm.Stream(m_dot=m_dot, T=temperature, p=pressure, fluid=esp.fluid),
            frequency=frequency,
        )
        for m_dot, temperature, pressure, frequency in rows
    ]


def traced(esp, rows, cache):
    """Evaluate the ESP on all rows in one traced NumPy call."""
    suction = Stream(m_dot=rows[:, 0], T=rows[:, 1], p=rows[:, 2], fluid=esp.fluid)
    return run(esp, {"suction": suction}, {"frequency": rows[:, 3]}, cache=cache)


def best_time(function, repeat):
    """Return the shortest wall time [s] of ``repeat`` calls and the last result."""
    times, result = [], None
    for _ in range(repeat):
        start = time.perf_counter()
        result = function()
        times.append(time.perf_counter() - start)
    return min(times), result


def check_agreement(results, graph_run):
    """Return the largest relative difference over every output; fail above ``RTOL``."""
    worst = 0.0
    for name in results[0].outputs:
        expected = np.array([result.outputs[name] for result in results], dtype=float)
        actual = np.asarray(graph_run.outputs[name], dtype=float)
        scale = np.maximum(np.abs(expected), np.finfo(float).tiny)
        worst = max(worst, float(np.max(np.abs(actual - expected) / scale)))
    if worst > RTOL:
        raise SystemExit(f"traced results differ by {worst:.3g} > {RTOL}")
    return worst


def benchmark_esp(repeat):
    """Print the ESP tick by tick and traced, with and without common-subexpression elimination."""
    esp, rows = load()
    trace_time, _ = best_time(lambda: GraphCache().graph(esp, {"suction": esp.fluid}), 1)
    merged, unmerged = GraphCache(), GraphCache(optimize=False)
    traced(esp, rows, merged)
    traced(esp, rows, unmerged)
    tick_time, results = best_time(lambda: untraced(esp, rows), repeat)
    plain_time, plain_run = best_time(lambda: traced(esp, rows, unmerged), repeat)
    graph_time, graph_run = best_time(lambda: traced(esp, rows, merged), repeat)
    worst = max(check_agreement(results, plain_run), check_agreement(results, graph_run))
    print(f"rows: {len(rows)}; nodes: {len(plain_run.graph.nodes)} -> {len(graph_run.graph.nodes)}")
    print(f"ESP tick by tick (untraced): {tick_time * 1e3:9.2f} ms")
    print(f"ESP trace (once, cached):    {trace_time * 1e3:9.2f} ms")
    print(f"ESP traced, no CSE:          {plain_time * 1e3:9.2f} ms")
    print(f"ESP traced, CSE:             {graph_time * 1e3:9.2f} ms")
    print(f"ESP speedup: {tick_time / graph_time:.0f}x; largest difference {worst:.3g}")


def replay(dataset):
    """Replay a freshly loaded plant over ``dataset`` and return the engine."""
    plant, engine = DoubletHeatPlant.load(PLANT), gm.Engine()
    engine.replay(plant, dataset)
    return engine


def benchmark_replay(repeat):
    """Print the plant replay on the old path and through the graph; the frames must be equal."""
    frame = pd.read_csv(DATASET, parse_dates=["time"])
    dataset = gm.Dataset.from_frame(frame, time_column="time")
    with graph.settings(traced=False):
        old_time, old = best_time(lambda: replay(dataset), repeat)
    new_time, new = best_time(lambda: replay(dataset), repeat)
    pd.testing.assert_frame_equal(new.results.to_frame(), old.results.to_frame(), check_exact=True)
    print(f"replay, old path:            {old_time:9.3f} s")
    print(f"replay, through the graph:   {new_time:9.3f} s")
    print(f"replay speedup: {old_time / new_time:.1f}x; frames identical; ", end="")
    print(f"twins not traced: {new.batch.reasons or 'none'}")


def main():
    """Run both benchmarks."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=5, help="timed repetitions per path")
    repeat = parser.parse_args().repeat
    benchmark_esp(repeat)
    benchmark_replay(repeat)


if __name__ == "__main__":
    main()
