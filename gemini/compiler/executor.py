"""The graph executor: trace a plant once, then evaluate whole time series of it.

``compile(plant)`` returns the ``GraphExecutor`` of ``plant``, which the engine runs when it is
built with ``compile=True``. The executor keeps the traced graphs of the plant in the plant's
``GraphCache``, so a second executor of one plant, and a second engine, trace nothing again until
a guard of the cache changes.
"""

from gemini.compiler.graph import evaluate, graph_cache, graph_feeds
from gemini.engine.executor import Executor


class GraphExecutor(Executor):
    """Evaluate a module as a computation graph: trace once, evaluate over all the rows."""

    def __init__(self, cache):
        """Trace into ``cache``, a ``GraphCache``."""
        self.cache = cache

    def prepare(self, module, streams, inputs, stepped):
        """Return the graph of ``module`` for the fluids of ``streams`` and its feeds."""
        fluids = {port: stream.fluid for port, stream in streams.items()}
        graph = self.cache.graph(module, fluids, stepped)
        return graph, graph_feeds(graph, module, streams, inputs)

    def evaluate(self, prepared, rows, context):
        """Return the ``Evaluation`` of the graph over ``rows`` rows."""
        graph, feeds = prepared
        return evaluate(graph, feeds, rows, context)


def compile(plant):
    """Return the executor that runs ``plant`` through its computation graphs."""
    return GraphExecutor(graph_cache(plant))
