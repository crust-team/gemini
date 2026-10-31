"""One twin evaluated over a block of ticks: its result columns, errors and new state.

``evaluate_twin`` builds the inlet streams and inputs of the ticks a ``Block`` lets through,
evaluates the twin's graph over them (``gemini.graph.evaluate``, on whichever backend is
selected), assesses the health of the rows that worked and spreads the columns over the ticks
of the chunk. A tick that cannot be evaluated has an error: an invalid inlet stream, the
exception of the failing row, or the exception of its health.
"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np

from gemini.engine.chunks import PathColumns
from gemini.engine.health import assess
from gemini.graph import evaluate, graph_feeds
from gemini.types import Stream
from gemini.types.flows import STREAM_FIELDS

UNCHANGED = object()
"""The ``state`` of an outcome that leaves the states of the run as they were."""


@dataclass
class Outcome:
    """What one twin gave over one chunk of ticks.

    ``tables`` maps result paths to their ``PathColumns`` over the chunk, ``errors`` maps a tick
    to its exception, ``selected`` lists the ticks that were evaluated and ``evaluation`` the
    array results of those (``results`` gives the tree row of one tick). ``state`` is the new
    state of the twin, or ``UNCHANGED``.
    """

    twin: object
    block: object
    selected: np.ndarray
    evaluation: object = None
    tables: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    state: object = UNCHANGED

    def result(self, tick):
        """Return the result tree of an evaluated tick, as plain Python values."""
        position = int(np.searchsorted(self.selected, tick))
        return self.evaluation.result.row(position)


def evaluate_twin(twin, block, cache, durations, state):
    """Return the ``Outcome`` of ``twin`` over ``block``.

    ``durations`` are the seconds of every tick of the chunk and ``state`` the state tree the
    twin starts from (``None`` for its initial states). ``cache`` is the ``GraphCache``.
    """
    selected = block.selected
    outcome = Outcome(twin, block, selected)
    for tick in np.flatnonzero(block.status < 0):
        outcome.errors[int(tick)] = block.stream_error(tick)
    if not selected.size:
        return outcome
    try:
        graph, feeds = _prepare(twin, block, selected, cache)
    except Exception as error:
        outcome.errors.update(dict.fromkeys(map(int, selected), error))
        return outcome
    context = {"dt": durations[selected], "states": _start_state(twin, block, selected, state)}
    evaluation = evaluate(graph, feeds, len(selected), context)
    outcome.evaluation = evaluation
    for position in np.flatnonzero(evaluation.failed):
        outcome.errors[int(selected[position])] = evaluation.error(int(position))
    ok = ~evaluation.failed
    if ok.any():
        _tabulate(outcome, ok)
        _advance(outcome, selected[ok][-1])
    return outcome


def _prepare(twin, block, selected, cache):
    """Return the graph of the twin and its feeds for the selected ticks."""
    module = twin.module
    streams = _streams(twin, block, selected)
    fluids = {port: stream.fluid for port, stream in streams.items()}
    graph = cache.graph(module, fluids, twin.stepped)
    inputs = {name: values[selected] for name, values in block.inputs.items()}
    return graph, graph_feeds(graph, module, streams, inputs)


def _streams(twin, block, selected):
    """Return the inlet streams of the selected ticks: arrays, or the plant's constants.

    An inlet with neither is refused as the module refuses a call without it.
    """
    streams = {}
    for port in twin.module._fed_inlets():
        if port in block.fluids:
            m_dot, temperature, pressure = (
                block.fields[port, name][selected] for name in STREAM_FIELDS
            )
            streams[port] = Stream._trusted(m_dot, temperature, pressure, block.fluids[port])
        elif port in twin.constants:
            streams[port] = _constant(twin, port, len(selected))
    if len(streams) < len(twin.module._fed_inlets()):
        twin.module._split_call_args((), streams)
    return streams


def _constant(twin, port, count):
    """Return an inlet that is not bound as a stream of ``count`` equal rows."""
    stream = twin.module._inlets[port].validate(twin.constants[port])
    return Stream._trusted(
        *(np.full(count, getattr(stream, name)) for name in STREAM_FIELDS), stream.fluid
    )


def _start_state(twin, block, selected, state):
    """Return the state a stepped twin starts from: the measured, the run's, else the initial.

    The initial state is passed explicitly, because a module may override ``step``.
    """
    if not twin.stepped:
        return None
    measured = twin.kinds("state")
    if measured:
        return {source.key: float(block.states[source.key][selected[0]]) for source in measured}
    return deepcopy(state) if state is not None else twin.module.initial_state()


def _advance(outcome, tick):
    """Take the state after the last row that worked: the measured one wins over the stepped."""
    twin = outcome.twin
    measured = twin.kinds("state")
    if measured:
        outcome.state = {s.key: float(outcome.block.states[s.key][tick]) for s in measured}
    elif outcome.evaluation.graph.stepped:
        outcome.state = outcome.evaluation.states


def _tabulate(outcome, ok):
    """Assess the health of the rows that worked and spread the columns over the chunk."""
    twin, block, selected = outcome.twin, outcome.block, outcome.selected
    result = _compressed(outcome.evaluation.result, ok)
    count = int(ok.sum())
    ticks = selected[ok]
    measured = {name: values[ticks] for name, values in block.measured.items()}
    leaves = _leaves(twin, result)
    healths = {
        path: assess(module, leaf, measured, count) for path, (module, leaf) in leaves.items()
    }
    bad = {position for _, errors in healths.values() for position in errors}
    for position in sorted(bad):
        outcome.errors[int(ticks[position])] = _first(healths, position)
    gone = ticks[sorted(bad)]
    for path, (_, leaf) in leaves.items():
        table = PathColumns.of(leaf, healths[path][0], np.ones(count, dtype=bool))
        outcome.tables[path] = table.spread(ticks, block.size).without(gone)


def _first(healths, position):
    """Return the exception of the first leaf whose health failed at ``position``."""
    return next(errors[position] for _, errors in healths.values() if position in errors)


def _leaves(twin, result):
    """Return ``{path: (module, result)}`` stored for a twin: itself, or a plant's leaves."""
    if not twin.leaves:
        return {twin.path: (twin.module, result)}
    return {path: (twin.module.get_submodule(path), leaf) for path, leaf in result.leaves().items()}


def _compressed(result, mask):
    """Return a tree of array results restricted to the rows of ``mask``."""
    if mask.all():
        return result
    return result.mapped(lambda value: value[mask] if np.ndim(value) else value)


class StepResults(Mapping):
    """The result trees of one tick by twin path, each built from the arrays when first asked."""

    def __init__(self, outcomes, tick):
        """Keep the outcomes that gave a result at ``tick`` (a position in the chunk)."""
        self._outcomes = {
            outcome.twin.path: outcome
            for outcome in outcomes
            if tick not in outcome.errors and tick in outcome.selected
        }
        self._tick = tick
        self._rows = {}

    def __getitem__(self, path):
        """Return the ``ModuleResult`` tree of a twin at this tick, as plain values."""
        if path not in self._rows:
            self._rows[path] = self._outcomes[path].result(self._tick)
        return self._rows[path]

    def __iter__(self):
        """Iterate the twin paths in evaluation order."""
        return iter(self._outcomes)

    def __len__(self):
        """Count the twins that gave a result."""
        return len(self._outcomes)
