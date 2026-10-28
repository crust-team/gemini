"""JSON-lines event tracing attached through the public module hooks."""

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter


class Callback:
    """Override any lifecycle hook; callbacks run in registration order between steps."""

    def on_run_start(self, engine):
        """Observe a new or resumed finite run."""

    def on_step_start(self, engine, sample):
        """Observe the next sample before any state is advanced."""

    def on_step_end(self, engine, sample):
        """Observe the completed sample after results and position have committed."""

    def on_error(self, engine, error):
        """Observe a failure with checkpoint-consistent state."""

    def on_run_end(self, engine):
        """Observe a successfully exhausted finite clock."""


class EventLog(Callback):
    """Append events to a file, or retain them in memory when no path is supplied."""

    def __init__(self, path=None):
        """Create a detached event sink."""
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = []
        self._handles = []
        self._starts = {}

    def log(self, kind, **payload):
        """Record a timestamped event, including future agent interactions."""
        event = {"ts": datetime.now(timezone.utc).isoformat(), "kind": kind, **payload}
        encoded = json.dumps(event, allow_nan=False)
        if self.path is None:
            self.events.append(event)
        else:
            with self.path.open("a") as handle:
                handle.write(encoded + "\n")
        return event

    def attach(self, plant):
        """Register pre/post hooks on every module without changing forward calculations."""
        self.detach()
        for path, module in plant.named_modules():
            module_path = path or plant.path

            def before(module, inputs, streams, path=module_path):
                self._starts[path] = perf_counter()

            def after(module, inputs, streams, result, path=module_path):
                start = self._starts.pop(path)
                self.log(
                    "forward",
                    module_path=path,
                    inputs=inputs.model_dump(mode="json"),
                    outputs=result.outputs.model_dump(mode="json"),
                    duration_ms=(perf_counter() - start) * 1000,
                )

            self._handles.extend(
                [module.register_forward_pre_hook(before), module.register_forward_hook(after)]
            )
        return self

    def detach(self):
        """Remove all owned hooks, leaving other observers intact."""
        for handle in self._handles:
            handle.remove()
        self._handles.clear()
        self._starts.clear()

    def on_run_start(self, engine):
        """Record run mode and attach equipment observers."""
        self.log("run_start", run_kind=engine.run_kind)
        self.attach(engine.plant)

    def on_step_end(self, engine, sample):
        """Record completed tick timing."""
        self.log("step_end", time=sample.t.isoformat(), dt=sample.dt)

    def on_error(self, engine, error):
        """Record errors and detach after interruptions."""
        self.log("error", message=str(error), error_type=type(error).__name__)
        if not isinstance(error, Exception) or engine.on_error == "raise":
            self.detach()

    def on_run_end(self, engine):
        """Record completion and remove owned observers."""
        self.log("run_end", steps=len(engine.results))
        self.detach()


class Progress(Callback):
    """Emit periodic progress through Python logging."""

    def __init__(self, every=100):
        """Choose a positive reporting interval in completed steps."""
        if every <= 0:
            raise ValueError("Progress interval must be positive")
        self.every = every

    def on_step_end(self, engine, sample):
        """Log every N completed steps."""
        import logging

        if len(engine.results) % self.every == 0:
            logging.getLogger(__name__).info(
                "%s: %d steps at %s", engine.run_kind, len(engine.results), sample.t.isoformat()
            )


class AlarmCollector(Callback):
    """Collect timestamped module alarms without repeatedly materialising the full frame."""

    def __init__(self):
        """Start an empty alarm list."""
        self.alarms = []

    def on_step_end(self, engine, sample):
        """Record alarms on the latest completed row."""
        for (path, field), value in engine.results._rows[-1].items():
            if field == "health_alarm" and value:
                self.alarms.append(dict(timestamp=sample.t, module=path))


class AutoCheckpoint(Callback):
    """Save at completed-step boundaries, every N steps or elapsed simulation duration."""

    def __init__(self, path, every=100):
        """Configure a positive step count or duration such as '1h'."""
        from gemini.core.engine.clock import duration

        self.path = path
        self.every = every if isinstance(every, int) else duration(every)
        if isinstance(every, int) and every <= 0:
            raise ValueError("Checkpoint interval must be positive")
        self._elapsed = 0.0

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
