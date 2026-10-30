"""Computation graphs of module calls: trace once, then evaluate whole time series at once.

``Tracer`` records one leaf module call as a ``Graph`` of ``Node`` objects, ``Interpreter``
evaluates a graph on a backend, ``GraphCache`` keeps one graph per module until a guard changes
and ``run`` evaluates a module over arrays, falling back to untraced calls on a graph break.
The design is described in ``.claude/docs/native-engine.md``.
"""

from gemini.graph.cache import GraphCache
from gemini.graph.graph import Graph
from gemini.graph.interpreter import Interpreter
from gemini.graph.node import Node
from gemini.graph.proxy import Proxy
from gemini.graph.runner import Run, run, run_function
from gemini.graph.setting import settings, traced_enabled
from gemini.graph.tracer import Tracer

__all__ = [
    "Graph",
    "GraphCache",
    "Interpreter",
    "Node",
    "Proxy",
    "Run",
    "Tracer",
    "run",
    "run_function",
    "settings",
    "traced_enabled",
]
