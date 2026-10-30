"""Benchmark the ESP over the July dataset: tick by tick against one traced NumPy call.

Run ``PYTHONPATH=. python scripts/benchmark_esp.py`` from the repository root. It
loads the shared doublet plant, evaluates its ESP on every row of the committed 2,976-row July
2024 dataset once per row (the current untraced path) and once as a traced graph on the NumPy
backend, checks that the results agree within the documented tolerance and prints the best of
``--repeat`` timings, the trace time and the speedup. It is a benchmark, not a test.
"""

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant
from gemini.core.types.flows import StreamState
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
    suction = StreamState(
        m_dot=rows[:, 0], T=rows[:, 1], p=rows[:, 2], fluid=esp.fluid, density=None
    )
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


def main():
    """Print the tick-by-tick time, the trace time, the traced time and the speedup."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=5, help="timed repetitions per path")
    repeat = parser.parse_args().repeat
    esp, rows = load()
    trace_time, _ = best_time(lambda: GraphCache().graph(esp, {"suction": esp.fluid}), 1)
    cache = GraphCache()
    traced(esp, rows, cache)
    tick_time, results = best_time(lambda: untraced(esp, rows), repeat)
    graph_time, graph_run = best_time(lambda: traced(esp, rows, cache), repeat)
    worst = check_agreement(results, graph_run)
    print(f"rows: {len(rows)}; graph nodes: {len(graph_run.graph.nodes)}")
    print(f"tick by tick (untraced): {tick_time * 1e3:9.2f} ms")
    print(f"trace (once, cached):    {trace_time * 1e3:9.2f} ms")
    print(f"traced NumPy call:       {graph_time * 1e3:9.2f} ms")
    print(f"speedup: {tick_time / graph_time:.0f}x; largest relative difference {worst:.3g}")


if __name__ == "__main__":
    main()
