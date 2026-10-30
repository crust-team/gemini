"""One finite execution loop for assumed inputs, measured history and periodic live windows."""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gemini.core import runtime
from gemini.core.data.loader import Loader
from gemini.core.engine import checkpoint as storage
from gemini.core.engine.clock import Clock
from gemini.core.engine.results import Results
from gemini.core.engine.runner import Runner
from gemini.core.engine.step import BindingPlan
from gemini.core.modules.module import class_path, import_class
from gemini.errors import CheckpointError, ConfigurationError
from gemini.graph import GraphCache
from gemini.utils.time import parse_duration, to_utc


def _live_ticks(position, start, end, step):
    """Return the ticks of a fixed grid in ``(position, end]``.

    The grid is anchored at the committed position, so it stays the same across live calls;
    the first call anchors it at the first supplied row.
    """
    step = parse_duration(step)
    if position is None:
        return pd.date_range(to_utc(start), to_utc(end), freq=step)
    ticks = pd.date_range(to_utc(position), to_utc(end), freq=step)
    return ticks[ticks > pd.Timestamp(to_utc(position))]


class Engine:
    """Run a plant on a finite clock, retaining all state needed for explicit checkpoint/resume."""

    def __init__(self, callbacks=None, on_error="record"):
        """Configure lifecycle callbacks and either recording or raising ordinary errors."""
        if on_error not in {"record", "raise"}:
            raise ConfigurationError(
                f"Engine: on_error = {on_error!r}; expected 'record' or 'raise'"
            )
        self.callbacks = list(callbacks or [])
        self.on_error = on_error
        self.plant = None
        self.results = None
        self.dataset = None
        self.clock = None
        self.run_kind = None
        self.position = None
        self.only = None
        self.module_states = {}
        self.runtime_state = runtime.state()
        self._dataset_fingerprint = None
        self._max_gap = None
        self._in_step = False
        self._graph_cache = GraphCache()
        self.graph_breaks = {}
        self.step_results = {}

    def simulate(self, plant, dataset, clock):
        """Evaluate the handwritten plant chain using assumed, root-bound inputs."""
        return self._run("simulate", plant, dataset, clock)

    def replay(self, plant, dataset, clock=None, start=None, end=None, only=None):
        """Evaluate measured equipment boundaries; infer observation ticks unless supplied."""
        if start is not None or end is not None:
            dataset = dataset.window(start, end)
            if clock is not None:
                clock = clock.window(start, end)
        if clock is None:
            clock = Clock.from_data(dataset)
        return self._run("replay", plant, dataset, clock, only=only)

    def live(self, plant, dataset, checkpoint, step=None, now=None, sink=None):
        """Process newly available ticks once, then save; an external scheduler calls again.

        Returns only this call's new rows. The engine and checkpoint retain cumulative results.
        The supplied plant is evaluated; an existing checkpoint contributes the committed
        position, results, module states, clock step and runtime settings, and must have been
        saved for a plant of the same class. Without ``step`` the ticks are the new rows; a
        call with fewer than two rows reuses the checkpointed step for its final interval.
        The checkpoint commits before sink delivery; external sinks should upsert by timestamp.
        """
        if Path(checkpoint).exists():
            self._restore_live(checkpoint, plant)
        else:
            self.position = None
            self.results = Results()
            self.module_states = {}
            self.clock = None
            self.runtime_state = runtime.state()
        now = to_utc(now) if now is not None else datetime.now(timezone.utc)
        clock = self._live_clock(dataset, step, now)
        offset = len(self.results)
        with self._saved_settings():
            self._run("live", plant, dataset, clock, continuing=True)
        self.save_checkpoint(checkpoint)
        fresh = self.results.slice(offset)
        if sink is not None and len(fresh):
            sink(fresh)
        return fresh

    def _restore_live(self, path, plant):
        """Take the run state of a live checkpoint saved for the supplied plant's class."""
        checkpoint = storage.load(path)
        if checkpoint.run_kind != "live":
            raise CheckpointError(f"{path}: run_kind = {checkpoint.run_kind!r}; expected 'live'")
        supplied = class_path(type(plant))
        if checkpoint.plant_class != supplied:
            raise CheckpointError(
                f"{path}: plant_class = {checkpoint.plant_class!r}; expected the supplied "
                f"plant's {supplied!r}"
            )
        self._restore(checkpoint, Path(path).parent)

    def _live_clock(self, dataset, step, now):
        """Return the unprocessed ticks up to ``now`` and the newest supplied row."""
        if not len(dataset):
            return Clock([])
        end = min(now, dataset.end)
        if step is not None:
            return Clock(_live_ticks(self.position, dataset.start, end, step), step)
        clock = Clock.from_data(dataset.window(end=end))
        if self.position is None:
            return clock
        if len(clock) < 2 and self.clock is not None:
            clock = Clock(clock.ticks, self.clock.step)
        return clock.after(self.position)

    def _saved_settings(self):
        """Return a context applying the precision and display units saved for this run.

        The default fluid is not re-applied: it only seeds newly built modules and streams,
        and the plant, built before the run, already carries its fluids.
        """
        values = dict(self.runtime_state)
        values.pop("default_fluid", None)
        return runtime.settings(**values)

    def _remaining(self, clock):
        """Return the ticks of ``clock`` after the committed position."""
        return clock.after(self.position) if self.position is not None else clock

    def _notify(self, method, *args):
        for callback in self.callbacks:
            getattr(callback, method)(self, *args)

    def _run(self, kind, plant, dataset, clock, only=None, continuing=False, max_gap=None):
        """Run the unfinished ticks of ``clock``; ``max_gap`` overrides the Loader default."""
        if not continuing:
            self.runtime_state = runtime.state()
        plan = BindingPlan(plant, dataset, kind, only, self.on_error)
        if not continuing:
            self.results = Results()
            self.module_states = {}
            self.position = None
        self.run_kind = kind
        self.plant = plant
        self.dataset = dataset
        self.clock = clock
        if not continuing or kind == "live" or self._dataset_fingerprint is None:
            self._dataset_fingerprint = dataset.fingerprint()
        self.only = list(only) if only is not None else None
        self.graph_breaks = {}
        remaining = self._remaining(clock)
        loader = Loader(
            dataset,
            remaining.ticks,
            columns=sorted(plan.columns),
            max_gap=max_gap,
            durations=remaining.durations,
        )
        self._max_gap = loader.max_gap
        try:
            self._notify("on_run_start")
            Runner(self, plan, loader.arrays()).run()
            self._notify("on_run_end")
        except BaseException as exc:
            self._in_step = False
            self._notify("on_error", exc)
            raise
        return self.results

    def save_checkpoint(self, path):
        """Save at a step boundary; assign engine.plant to save before the first run."""
        if self.plant is None:
            raise CheckpointError(
                f"{path}: engine.plant = None; expected a plant assigned or a started run"
            )
        if self._in_step:
            raise CheckpointError(f"{path}: called inside a step; expected a completed step")
        checkpoint = storage.Checkpoint(
            run_kind=self.run_kind,
            plant_class=class_path(type(self.plant)),
            plant=self.plant.to_dict(),
            module_states=self.module_states,
            clock=self.clock.describe() if self.clock is not None else None,
            position=self.position,
            dataset_fingerprint=self._dataset_fingerprint,
            only=self.only,
            on_error=self.on_error,
            runtime=self.runtime_state,
        )
        storage.save(path, checkpoint, self.results, self._unfinished_rows(), self._max_gap)

    def _unfinished_rows(self):
        """Return the rows a resumed simulation or replay still reads, or None.

        Rows up to ``max_gap`` before the position stay because a held previous row may still
        supply the next ticks. Live checkpoints store no rows: every call supplies its own.
        """
        if self.run_kind not in {"simulate", "replay"} or self.dataset is None:
            return None
        if self.position is None or self._max_gap is None:
            return self.dataset
        if self.clock is None or not len(self._remaining(self.clock)):
            return None
        return self.dataset.window(start=self.position - self._max_gap)

    @classmethod
    def load_checkpoint(cls, path, callbacks=None):
        """Restore a plant, dataset handle, finite schedule, states and completed results."""
        checkpoint = storage.load(path)
        engine = cls(callbacks, checkpoint.on_error)
        plant_class = import_class(checkpoint.plant_class)
        engine.plant = plant_class.from_dict(checkpoint.plant)
        engine._restore(checkpoint, Path(path).parent)
        return engine

    def _restore(self, checkpoint, folder):
        """Assign the saved run state; the plant, callbacks and error policy stay unchanged."""
        self.run_kind = checkpoint.run_kind
        self.position = checkpoint.position
        self.module_states = checkpoint.module_states
        self.only = checkpoint.only
        self.runtime_state = checkpoint.runtime or runtime.state()
        self.clock = Clock.reopen(checkpoint.clock) if checkpoint.clock is not None else None
        self._dataset_fingerprint = checkpoint.dataset_fingerprint
        self.dataset = None
        self._max_gap = None
        if checkpoint.remaining_data_file:
            self.dataset, self._max_gap = storage.read_dataset(
                folder / checkpoint.remaining_data_file
            )
        self.results = (
            Results.load(folder / checkpoint.results_file) if checkpoint.results_file else Results()
        )

    def resume(self):
        """Continue strictly after the saved position, or return stored results when finished."""
        if self.run_kind is None:
            return self.results if self.results is not None else Results()
        if self.clock is None:
            raise CheckpointError(f"{self.run_kind} checkpoint: clock = None; expected a clock")
        remaining = self._remaining(self.clock)
        if not len(remaining):
            return self.results
        if self.dataset is None:
            raise CheckpointError(
                f"{self.run_kind} checkpoint: {len(remaining)} unfinished ticks and no stored "
                "rows; expected the rows saved with an unfinished simulation or replay"
            )
        with self._saved_settings():
            return self._run(
                self.run_kind,
                self.plant,
                self.dataset,
                self.clock,
                only=self.only,
                continuing=True,
                max_gap=self._max_gap,
            )
