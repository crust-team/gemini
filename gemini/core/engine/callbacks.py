"""Engine lifecycle callbacks: a JSON-lines event log and periodic checkpoints."""

import json
import numbers
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from time import perf_counter

from pydantic_core import to_jsonable_python

from gemini.errors import ConfigurationError
from gemini.utils.hooks import observer
from gemini.utils.time import parse_duration


class Callback:
    """Override any lifecycle hook; callbacks run in registration order between steps.

    ``on_error`` observes only a failure that ends the run. Module failures recorded under
    ``on_error="record"`` are results: they are in ``engine.results.errors`` when
    ``on_step_end`` runs.
    """

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

    Every module is observed through a forward pre-hook and a forward hook, both marked as
    observers so the graph engine replays them per row, attached at run
    start and removed when the run ends or fails. Logging never changes a run: non-finite
    floats are written as ``NaN``/``Infinity`` and other unknown values as strings.
    """

    def __init__(self, path=None):
        """Create a detached event sink."""
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = []
        self._handles = []
        self._starts = {}
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

    def attach(self, plant):
        """Register pre/post hooks on every module without changing forward calculations."""
        self.detach()
        for path, module in plant.named_modules():
            module_path = path or plant.path
            before = observer(partial(self._before, module_path))
            after = observer(partial(self._after, module_path))
            self._handles.append(module.register_forward_pre_hook(before))
            self._handles.append(module.register_forward_hook(after))
        return self

    def _before(self, path, module, inlets):
        """Remember the start time and the inlets, controls and boundaries of one call."""
        inputs = dict(inlets) | {
            name: getattr(module, name) for name in module.inputs(recurse=False)
        }
        self._starts[path] = perf_counter(), _jsonable(inputs)

    def _after(self, path, module, inlets, outlets):
        """Log one module call with its inputs, outputs and duration."""
        start, inputs = self._starts.pop(path)
        self.log(
            "forward",
            module_path=path,
            inputs=inputs,
            outputs=_jsonable(
                {name: getattr(module, name) for name in module.outputs(recurse=False)}
            ),
            duration_ms=(perf_counter() - start) * 1000,
        )

    def detach(self):
        """Remove all owned hooks, leaving other observers intact."""
        for handle in self._handles:
            handle.remove()
        self._handles.clear()
        self._starts.clear()

    def on_run_start(self, engine):
        """Record run mode and attach equipment observers."""
        self.log("run_start", run_kind=engine.run_kind)
        self._logged_errors = len(engine.results.errors)
        self.attach(engine.plant)

    def on_step_end(self, engine, sample):
        """Record the step's recorded module errors, then the completed tick timing."""
        for error in engine.results.errors[self._logged_errors :]:
            self.log(
                "error", module=error["module"], message=error["message"], error_type=error["type"]
            )
        self._logged_errors = len(engine.results.errors)
        self.log("step_end", time=sample.t.isoformat(), dt=sample.dt)

    def on_error(self, engine, error):
        """Record the failure that ended the run and remove owned observers."""
        self.log("error", message=str(error), error_type=type(error).__name__)
        self.detach()

    def on_run_end(self, engine):
        """Record completion and remove owned observers."""
        self.log("run_end", steps=len(engine.results))
        self.detach()


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
