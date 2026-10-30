"""Run one scenario on every backend and compare what each reports with the reference.

``BACKENDS`` is the one list of backends under test: the first is the reference and every other
one is compared with it. Every parity test loops over this list and none names a backend, so a new
backend is added here and nowhere else. ``on_each_backend`` runs a callable once per backend, with
the backend forced for the whole call (tracing included), and returns the outcomes by name.

For whole engine runs ``run_engine`` records a ``Snapshot`` of everything a run reports: the
frame, skips, errors, summary, plant inputs, module states, graph breaks, the hooks a callback
sees with the ``ModuleResult`` tree of every tick (``engine.step_results``), the ``EventLog``
events without their timestamps and the error that ended the run. ``assert_snapshots_match``
compares two of them: structure and Python types exactly, floats within ``RTOL``.
"""

import contextlib
import copy
import dataclasses
import math

import pandas as pd

import gemini as gm
from gemini import backends
from gemini.engine.callbacks import Callback, EventLog
from gemini.types.flows import STREAM_FIELDS

RTOL = 1e-12
"""The documented relative tolerance of a backend against the reference."""

BACKENDS = ("python", "numpy")
"""The backends under test; the first is the reference."""

REFERENCE = BACKENDS[0]
TIMING_KEYS = ("ts", "duration_ms")


@contextlib.contextmanager
def forced(backend):
    """Force ``backend`` for the block, as ``gemini.backends.settings`` does."""
    with backends.settings(backend=backend):
        yield


def on_each_backend(scenario):
    """Return ``{backend: scenario(backend)}`` with each backend forced during its call."""
    outcomes = {}
    for backend in BACKENDS:
        with forced(backend):
            outcomes[backend] = scenario(backend)
    return outcomes


def others(outcomes):
    """Return ``(name, outcome)`` of every backend but the reference."""
    return [(name, outcome) for name, outcome in outcomes.items() if name != REFERENCE]


def assert_equal(actual, expected, label="value"):
    """Assert two nested values have the same structure and types and floats within ``RTOL``.

    Dictionaries compare with their key order, lists and tuples item by item; an exact type
    mismatch (``float`` against ``numpy.float64``, ``bool`` against ``int``) fails.
    """
    assert type(actual) is type(
        expected
    ), f"{label}: {type(actual).__name__} against {type(expected).__name__}"
    if isinstance(expected, dict):
        assert list(actual) == list(expected), f"{label}: keys {list(actual)} != {list(expected)}"
        for key, value in expected.items():
            assert_equal(actual[key], value, f"{label}.{key}")
    elif isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected), f"{label}: length"
        for index, value in enumerate(expected):
            assert_equal(actual[index], value, f"{label}[{index}]")
    elif isinstance(expected, float):
        same = actual == expected or (math.isnan(actual) and math.isnan(expected))
        assert same or math.isclose(
            actual, expected, rel_tol=RTOL, abs_tol=0
        ), f"{label}: {actual!r} != {expected!r}"
    else:
        assert actual == expected, f"{label}: {actual!r} != {expected!r}"


def plain(result):
    """Return a ``ModuleResult`` tree as nested dictionaries of its values, children included."""
    return {
        "outputs": dict(result.outputs.items()),
        "outlets": {port: _stream(stream) for port, stream in result.outlets.items()},
        "inlets": {port: _stream(stream) for port, stream in result.inlets.items()},
        "inputs": dict(result.inputs),
        "children": {name: plain(child) for name, child in result.children.items()},
        "called": [name for name, _ in result.call_records],
        "is_leaf": result.is_leaf,
    }


def _stream(stream):
    return {field: getattr(stream, field) for field in (*STREAM_FIELDS, "fluid")}


class Recorder(Callback):
    """Record every hook a callback receives and the engine's view at the end of each tick."""

    def __init__(self):
        """Start with no hooks seen."""
        self.hooks = []
        self.steps = []

    def on_run_start(self, engine):
        """Record the start."""
        self.hooks.append(("on_run_start",))

    def on_step_start(self, engine, sample):
        """Record the tick about to be evaluated."""
        self.hooks.append(("on_step_start", sample.t.isoformat(), sample.dt))

    def on_step_end(self, engine, sample):
        """Record the tick's result trees, position, states and the counts of results and errors."""
        self.hooks.append(("on_step_end", sample.t.isoformat(), sample.dt))
        self.steps.append(
            {
                "trees": {path: plain(result) for path, result in engine.step_results.items()},
                "position": engine.position.isoformat(),
                "states": copy.deepcopy(engine.module_states),
                "results": len(engine.results),
                "errors": len(engine.results.failures),
            }
        )

    def on_error(self, engine, error):
        """Record the failure that ends the run."""
        self.hooks.append(("on_error", type(error).__name__, str(error)))

    def on_run_end(self, engine):
        """Record the end."""
        self.hooks.append(("on_run_end",))


@dataclasses.dataclass
class Snapshot:
    """Everything one engine run reports."""

    frame: pd.DataFrame
    skips: dict
    errors: list
    summary: pd.DataFrame
    inputs: dict
    states: dict
    position: object
    breaks: dict
    hooks: list
    steps: list
    events: list
    failure: tuple | None = None


def _events(log):
    return [{k: v for k, v in event.items() if k not in TIMING_KEYS} for event in log.events]


def _failure(error):
    cause = error.__cause__
    return (
        type(error).__name__,
        str(error),
        type(cause).__name__ if cause else None,
        str(cause) if cause else None,
    )


def snapshot(engine, plant, recorder, log, failure=None):
    """Return the ``Snapshot`` of an engine after a run, whole or ended by ``failure``."""
    results = engine.results
    return Snapshot(
        frame=results.to_frame(),
        skips=copy.deepcopy(results.skip_counts),
        errors=copy.deepcopy(results.failures),
        summary=pd.DataFrame(results.to_frame(table="energy")),
        inputs={path: dict(module._input_values) for path, module in plant.named_modules()},
        states=copy.deepcopy(engine.module_states),
        position=engine.position,
        breaks=copy.deepcopy(engine.graph_breaks),
        hooks=recorder.hooks,
        steps=recorder.steps,
        events=_events(log),
        failure=failure,
    )


def run_engine(plant, dataset, mode="replay", *args, callbacks=(), on_error="record", **kwargs):
    """Run ``mode`` (``replay`` or ``simulate``) on the current backend and return a ``Snapshot``.

    An ``Exception`` that ends the run is part of the snapshot. ``callbacks`` come after the
    ``Recorder`` and the ``EventLog``, which the snapshot reads.
    """
    recorder, log = Recorder(), EventLog()
    backend = backends.forced_name() or "numpy"
    engine = gm.Engine(plant, backend, [log, recorder, *callbacks], on_error)
    failure = None
    try:
        getattr(engine, mode)(dataset, *args, **kwargs)
    except Exception as error:
        failure = _failure(error)
    return snapshot(engine, plant, recorder, log, failure)


def assert_frames_match(actual, expected):
    """Assert two result frames have the same columns, dtypes, NaN positions and values."""
    pd.testing.assert_frame_equal(actual, expected, check_exact=False, rtol=RTOL, atol=0)


def assert_snapshots_match(actual, expected):
    """Assert two snapshots are the same run: tables, errors, hooks, result trees and events."""
    assert_frames_match(actual.frame, expected.frame)
    assert actual.skips == expected.skips
    assert_equal(actual.errors, expected.errors, "errors")
    assert_frames_match(actual.summary, expected.summary)
    assert_equal(actual.inputs, expected.inputs, "inputs")
    assert_equal(actual.states, expected.states, "states")
    assert actual.position == expected.position
    assert actual.breaks == expected.breaks
    assert actual.failure == expected.failure
    assert actual.hooks == expected.hooks
    assert_equal(actual.steps, expected.steps, "steps")
    assert_equal(actual.events, expected.events, "events")


def assert_runs_match(outcomes):
    """Assert every backend's snapshot equals the reference's."""
    for name, outcome in others(outcomes):
        try:
            assert_snapshots_match(outcome, outcomes[REFERENCE])
        except AssertionError as error:
            raise AssertionError(f"{name} against {REFERENCE}: {error}") from error
