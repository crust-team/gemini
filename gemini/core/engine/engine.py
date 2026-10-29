"""One finite execution loop for assumed inputs, measured history and periodic live windows."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from gemini.core import runtime
from gemini.core.data.loader import Loader
from gemini.core.engine import checkpoint as storage
from gemini.core.engine.clock import Clock, LiveClock
from gemini.core.engine.results import Results
from gemini.core.engine.step import BindingPlan, chained_step, twin_step
from gemini.core.modules.module import Module
from gemini.utils.time import to_utc


class Engine:
    """Run a plant on a finite clock, retaining all state needed for explicit checkpoint/resume."""

    def __init__(self, callbacks=None, on_error="record"):
        """Configure lifecycle callbacks and either recording or raising ordinary errors."""
        if on_error not in {"record", "raise"}:
            raise ValueError("on_error must be 'record' or 'raise'")
        self.callbacks, self.on_error = list(callbacks or []), on_error
        self.plant = self.results = self.dataset = self.clock = None
        self.run_kind = self.position = self.only = None
        self.module_states = {}
        self._dataset_fingerprint = None
        self._in_step = False
        self.runtime_state = runtime.state()

    def simulate(self, plant, dataset, clock):
        """Evaluate the handwritten plant chain using assumed, root-bound inputs."""
        return self._run("simulate", plant, dataset, clock, chained_step)

    def replay(self, plant, dataset, clock=None, start=None, end=None, only=None):
        """Evaluate measured equipment boundaries; infer observation ticks unless supplied."""
        if start is not None or end is not None:
            dataset = dataset.window(start, end)
        if clock is not None and (start is not None or end is not None):
            clock = Clock(
                [
                    t
                    for t in clock
                    if (start is None or t >= to_utc(start)) and (end is None or t <= to_utc(end))
                ],
                clock.step,
            )
        return self._run(
            "replay",
            plant,
            dataset,
            clock if clock is not None else Clock.from_data(dataset),
            twin_step,
            only=only,
        )

    def live(self, plant, dataset, checkpoint, step=None, now=None, sink=None):
        """Process newly available ticks once, then save; an external scheduler calls again.

        Returns only this call's new rows. The engine and checkpoint retain cumulative results.
        The checkpoint commits before sink delivery; external sinks should upsert by timestamp.
        """
        if Path(checkpoint).exists():
            restored = self.load_checkpoint(checkpoint, callbacks=self.callbacks)
            if restored.run_kind != "live":
                raise ValueError("live requires a live checkpoint")
            if restored.plant.name != plant.name:
                raise ValueError("Live checkpoint plant type differs from the supplied plant")
            self.__dict__.update(restored.__dict__)
            plant = self.plant
        else:
            self.position, self.results, self.module_states = None, Results(), {}
        now = to_utc(now) if now is not None else datetime.now(timezone.utc)
        latest = dataset.end
        if latest is None or dataset.start is None:
            clock = Clock([])
        elif step is None:
            clock = Clock.from_data(dataset.window(end=min(now, latest)))
            if self.position is not None:
                clock = clock.after(self.position)
        else:
            clock = LiveClock(self.position, min(now, latest), step, start=dataset.start)
        offset = len(self.results)
        self._run("live", plant, dataset, clock, twin_step, continuing=True)
        self.save_checkpoint(checkpoint)
        fresh = self.results.slice(offset)
        if sink is not None and len(fresh):
            sink(fresh)
        return fresh

    def _notify(self, method, *args):
        for callback in self.callbacks:
            getattr(callback, method)(self, *args)

    def _run(self, kind, plant, dataset, clock, step_fn, only=None, continuing=False):
        if not continuing:
            self.runtime_state = runtime.state()
        plan = BindingPlan(plant, dataset, kind, only, self.on_error)
        if not continuing:
            self.results, self.module_states, self.position = Results(), {}, None
        self.run_kind, self.plant, self.dataset, self.clock = kind, plant, dataset, clock
        if not continuing or kind == "live" or self._dataset_fingerprint is None:
            self._dataset_fingerprint = dataset.fingerprint()
        self.only = list(only) if only is not None else None
        remaining = clock.after(self.position) if self.position is not None else clock
        loader = Loader(dataset, remaining, columns=sorted(plan.columns))
        try:
            self._notify("on_run_start")
            for sample in loader:
                self._notify("on_step_start", sample)
                previous_states = deepcopy(self.module_states)
                self._in_step = True
                try:
                    output = step_fn(plant, sample, self.module_states, plan)
                except BaseException as exc:
                    self.module_states = previous_states
                    self._in_step = False
                    if not isinstance(exc, Exception) or self.on_error == "raise":
                        raise
                    plan.skips = {}
                    plan.errors = [dict(module="", message=str(exc), type=type(exc).__name__)]
                    output = {}
                self.results.append(sample.t, output, sample.dt, plan.skips, plan.errors)
                self.position = sample.t
                self._in_step = False
                for error in plan.errors:
                    self._notify("on_error", RuntimeError(f"{error['module']}: {error['message']}"))
                self._notify("on_step_end", sample)
            self._notify("on_run_end")
        except BaseException as exc:
            self._in_step = False
            self._notify("on_error", exc)
            raise
        return self.results

    def save_checkpoint(self, path):
        """Save at a step boundary; assign engine.plant to save before the first run."""
        if self.plant is None:
            raise ValueError("Set engine.plant or start a run before saving a checkpoint")
        if self._in_step:
            raise RuntimeError("Checkpoints are only valid between completed steps")
        checkpoint = storage.Checkpoint(
            run_kind=self.run_kind,
            plant_class=Module._class_name(type(self.plant)),
            plant=self.plant.to_dict(),
            module_states=self.module_states,
            clock=self.clock.describe() if self.clock is not None else None,
            position=self.position,
            dataset_fingerprint=self._dataset_fingerprint,
            only=self.only,
            on_error=self.on_error,
            runtime=self.runtime_state,
        )
        remaining = None
        if self.run_kind in {"simulate", "replay"} and self.dataset is not None:
            remaining = self.dataset.after(self.position)
        storage.save(path, checkpoint, self.results, remaining)

    @classmethod
    def load_checkpoint(cls, path, callbacks=None):
        """Restore a plant, dataset handle, finite schedule, states and completed results."""
        checkpoint = storage.load(path)
        engine = cls(callbacks, checkpoint.on_error)
        plant_class = Module._import_class(checkpoint.plant_class)
        engine.plant = plant_class.from_dict(checkpoint.plant)
        engine.run_kind, engine.position = checkpoint.run_kind, checkpoint.position
        engine.module_states, engine.only = checkpoint.module_states, checkpoint.only
        engine.runtime_state = checkpoint.runtime or runtime.state()
        engine.clock = Clock.reopen(checkpoint.clock) if checkpoint.clock is not None else None
        engine._dataset_fingerprint = checkpoint.dataset_fingerprint
        engine.dataset = (
            storage.read_dataset(Path(path).parent / checkpoint.remaining_data_file)
            if checkpoint.remaining_data_file
            else None
        )
        engine.results = (
            Results.load(Path(path).parent / checkpoint.results_file)
            if checkpoint.results_file
            else Results()
        )
        return engine

    def resume(self):
        """Continue strictly after the saved position, or return stored results when finished."""
        if self.run_kind is None:
            return self.results if self.results is not None else Results()
        if self.clock is None:
            raise ValueError("Checkpoint does not contain a resumable run")
        if not len(self.clock):
            return self.results
        if self.position is not None and not len(self.clock.after(self.position)):
            return self.results
        if self.dataset is None:
            raise ValueError("Checkpoint has unfinished ticks but no remaining in-memory data")
        step_fn = chained_step if self.run_kind == "simulate" else twin_step
        values = self.runtime_state.copy()
        values.pop("default_fluid", None)
        with runtime.settings(**values):
            return self._run(
                self.run_kind,
                self.plant,
                self.dataset,
                self.clock,
                step_fn,
                only=self.only,
                continuing=True,
            )
