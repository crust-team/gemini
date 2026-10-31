"""The eager executor: ``forward`` on arrays over the whole chunk, row by row only when it must.

A module without state, loop, constraint or pre-hook is called once on the arrays of the chunk
(the NumPy kernels do the rows at once). Any other module, a run on the Python backend and a
precision other than float64 call the module for real on each row (``gemini.engine.rows``), and so
does an array call that raised: the call of each row then gives the exception of its own row, so
the rows that work are never lost to one that fails.
"""

from typing import NamedTuple

import numpy as np

from gemini import runtime
from gemini.engine.evaluation import Evaluation, converter, typed
from gemini.engine.executor import EAGER, Executor, register_executor
from gemini.engine.rows import applied, inlet_feeds, run_rows, stacked
from gemini.errors import RunError
from gemini.ops import kernels


class Call(NamedTuple):
    """A module with the inlet streams and inputs of the selected rows."""

    module: object
    streams: dict
    inputs: dict
    stepped: bool


class EagerExecutor(Executor):
    """Evaluate a module as a direct call does, over arrays when it can."""

    def prepare(self, module, streams, inputs, stepped):
        """Keep the call; nothing is traced or compiled."""
        return Call(module, streams, inputs, stepped)

    def evaluate(self, prepared, rows, context):
        """Return the evaluation over ``rows``: one array call, else one call per row."""
        if not _by_rows(prepared.module):
            try:
                return self._arrays(prepared, rows)
            except Exception:
                pass
        return self._rows(prepared, rows, context)

    def _arrays(self, call, rows):
        with applied(call.module, call.inputs):
            result = call.module(call.streams)
        tree = typed(result.mapped(converter(rows)))
        return Evaluation(rows, np.zeros(rows, dtype=bool), tree, _no_error)

    def _rows(self, call, rows, context):
        module = call.module
        stepped = call.stepped and any(member.stateful for member in module.modules())
        fluids = {port: stream.fluid for port, stream in call.streams.items()}
        feeds = inlet_feeds(call.streams) | call.inputs
        results, errors, states = run_rows(module, fluids, feeds, rows, context, stepped)
        failed = np.ones(rows, dtype=bool)
        failed[list(results)] = False
        result = stacked(results, rows)
        tree = None if result is None else typed(result)
        return Evaluation(rows, failed, tree, errors.__getitem__, states, stepped)


def _by_rows(module):
    """Return whether ``module`` must be called row by row."""
    if kernels.forced_name() == "python" or runtime.get_precision() != "float64":
        return True
    return any(
        member.stateful or member._iterates() or member._pre_hooks for member in module.modules()
    )


def _no_error(row):
    raise RunError(f"row {row}: did not fail; expected a failed row", code="step")


register_executor(EAGER, lambda plant: EagerExecutor())
