"""JSON-lines event tracing attached through the public module hooks."""

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter


class EventLog:
    """Append events to a file, or retain them in memory when no path is supplied."""

    def __init__(self, path=None):
        """Create a detached event sink."""
        self.path = Path(path) if path is not None else None
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
