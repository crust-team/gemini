"""Interrupt between completed steps and resume in a fresh engine."""

from pathlib import Path

import gemini as gm

DATA = Path(__file__).resolve().parents[1] / "datasets/geothermal_doublet"
plant = gm.load_plant(DATA)

from tempfile import TemporaryDirectory

from gemini.core.engine.callbacks import AutoCheckpoint, Callback


class Pause(Callback):
    """Model an external cancellation after five committed observations."""

    def on_step_end(self, engine, sample):
        """Interrupt after the automatic checkpoint has saved this boundary."""
        if len(engine.results) == 5:
            raise KeyboardInterrupt


data = gm.Dataset.from_csv(DATA / "geothermal_example_dataset.csv").window(
    end="2024-06-07T02:45:00Z"
)
with TemporaryDirectory() as directory:
    checkpoint = Path(directory) / "replay.ckpt"
    engine = gm.Engine([AutoCheckpoint(checkpoint, every=5), Pause()])
    try:
        engine.replay(plant, data)
    except KeyboardInterrupt:
        print("Paused with", len(engine.results), "completed rows")
    restored = gm.Engine.load_checkpoint(checkpoint)
    print("Resumed to", len(restored.resume()), "rows")
