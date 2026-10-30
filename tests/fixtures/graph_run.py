"""Run a graph on a backend through ``evaluate`` and raise the first failing row."""

import numpy as np

from gemini import backends
from gemini.graph import evaluate


def graph_outputs(graph, feeds, backend="numpy"):
    """Return the output arrays of ``graph`` by name; plain numbers when every feed is a scalar."""
    rows = max([np.size(value) for value in feeds.values()], default=1)
    with backends.settings(backend=backend):
        evaluation = evaluate(graph, feeds, rows)
    evaluation.raise_first()
    scalar = all(np.ndim(value) == 0 for value in feeds.values())
    return {
        name: evaluation.output(name)[0] if scalar else evaluation.output(name)
        for name in graph.outputs
    }
