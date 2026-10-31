"""Computation graphs of module calls: trace once, then evaluate whole time series at once.

``Tracer`` records one module call as a ``Graph`` of ``Node`` objects (a root that cannot be
traced is a root break graph), ``Interpreter`` evaluates a graph on a backend, ``evaluate`` gives
the ``Evaluation`` of a graph over the rows of a chunk on either backend, ``GraphCache`` keeps one
graph per module until a guard changes and ``run`` evaluates a module over arrays.
The design is described in ``.claude/docs/native-engine.md``.
"""

from gemini.compiler.graph.cache import GraphCache, graph_cache
from gemini.compiler.graph.evaluation import Evaluation, evaluate
from gemini.compiler.graph.graph import Graph
from gemini.compiler.graph.interpreter import Interpreter
from gemini.compiler.graph.node import Node
from gemini.compiler.graph.proxy import Proxy
from gemini.compiler.graph.runner import Run, graph_feeds, run, run_function
from gemini.compiler.graph.tracer import Tracer

__all__ = [
    "Evaluation",
    "Graph",
    "GraphCache",
    "graph_cache",
    "Interpreter",
    "Node",
    "Proxy",
    "Run",
    "Tracer",
    "evaluate",
    "graph_feeds",
    "run",
    "run_function",
]
