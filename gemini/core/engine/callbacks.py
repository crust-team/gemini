"""Engine lifecycle callbacks: a JSON-lines event log and periodic checkpoints."""

import json
import numbers
from datetime import datetime, timezone
from pathlib import Path

from pydantic_core import to_jsonable_python

from gemini.errors import ConfigurationError
from gemini.utils.strings import join_path
from gemini.utils.time import parse_duration


class Callback:
    """Override any lifecycle hook; callbacks run in registration order between steps.

    A callback that changes the run (the plant, its parameters or inputs, the dataset) sets the
    class attribute ``changes_run = True``: the engine then evaluates one tick at a time, calling
    ``on_step_start`` before the tick is evaluated. Otherwise the engine may evaluate many ticks
    at once and replays the callbacks from the results.

    ``on_error`` observes only a failure that ends the run. Module failures recorded under
    ``on_error="record"`` are results: they are in ``engine.results.errors`` when
    ``on_step_end`` runs.
    """

    changes_run = False

    def on_run_start(self, engine):
        """Observe a new or resumed finite run."""

    def on_step_start(self, engine, sample):
        """Observe the next sample before any state is advanced."""

    def on_step_end(self, engine, sample):
        """Observe the completed sample after results and position have committed."""

    def on_error(self, engine, error):
        """Observe the failure that ends a run, with checkpoint-consistent state."""

    def on_run_end(self, engine):
        """Observe a successfully exhausted finite clock."""


def _jsonable(value):
    """Return ``value`` as JSON-compatible data; unknown objects become their ``str``."""
    return to_jsonable_python(value, fallback=str)


class EventLog(Callback):
    """Append events to a JSON-lines file, or retain them in memory when no path is supplied.

    After each tick it logs one ``forward`` event for every module call of the tick's results
    (``engine.step_results``), children before the module that called them, with the call's
    inlets and inputs and its outputs. Logging never changes a run: non-finite floats are
    written as ``NaN``/``Infinity`` and other unknown values as strings.
    """

    def __init__(self, path=None):
        """Create an event sink."""
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = []
        self._logged_errors = 0

    def log(self, kind, **payload):
        """Record a timestamped event, including future agent interactions."""
        event = {"ts": datetime.now(timezone.utc).isoformat(), "kind": kind, **payload}
        if self.path is None:
            self.events.append(event)
            return event
        with self.path.open("a") as handle:
            handle.write(json.dumps(event) + "\n")
        return event

    def _calls(self, plant, path, result):
        """Log the calls of a result tree in completion order: children first, then itself."""
        for name, child in result.call_records:
            self._calls(plant, join_path(path, name), child)
        module = plant.get_submodule(path)
        inputs = dict(result.inlets) | {
            name: result.inputs[name] for name in module.inputs(recurse=False)
        }
        outputs = {name: result.outputs[name] for name in module.outputs(recurse=False)}
        self.log(
            "forward",
            module_path=path or plant.path,
            inputs=_jsonable(inputs),
            outputs=_jsonable(outputs),
        )

    def on_run_start(self, engine):
        """Record run mode."""
        self.log("run_start", run_kind=engine.run_kind)
        self._logged_errors = len(engine.results.errors)

    def on_step_end(self, engine, sample):
        """Record the tick's module calls, its recorded errors, then the completed tick timing."""
        for path, result in engine.step_results.items():
            self._calls(engine.plant, path, result)
        for error in engine.results.errors[self._logged_errors :]:
            self.log(
                "error", module=error["module"], message=error["message"], error_type=error["type"]
            )
        self._logged_errors = len(engine.results.errors)
        self.log("step_end", time=sample.t.isoformat(), dt=sample.dt)

    def on_error(self, engine, error):
        """Record the failure that ended the run."""
        self.log("error", message=str(error), error_type=type(error).__name__)

    def on_run_end(self, engine):
        """Record completion."""
        self.log("run_end", steps=len(engine.results))


class AutoCheckpoint(Callback):
    """Save at completed-step boundaries, every N steps or elapsed simulation duration."""

    def __init__(self, path, every=100):
        """Configure a positive step count (any integer type) or a duration such as '1h'."""
        self.path = path
        self._elapsed = 0.0
        if not isinstance(every, numbers.Integral):
            self.every = parse_duration(every)
            return
        if every <= 0:
            raise ConfigurationError(
                f"AutoCheckpoint: every = {every!r}; expected a positive step count or duration"
            )
        self.every = int(every)

    def on_step_end(self, engine, sample):
        """Write only after the engine has committed position, states and results."""
        self._elapsed += sample.dt
        due = (
            len(engine.results) % self.every == 0
            if isinstance(self.every, int)
            else self._elapsed >= self.every.total_seconds()
        )
        if due:
            engine.save_checkpoint(self.path)
            self._elapsed = 0.0
