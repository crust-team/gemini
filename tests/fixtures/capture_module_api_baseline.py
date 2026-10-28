"""Capture phase-0 state and results before the module API migration.

Run only from the untouched ``refactor`` implementation.  The generated fixtures are
comparison inputs for the new API and must not be regenerated after the migration.
"""

import json
from pathlib import Path
from time import perf_counter

import pandas as pd

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

ROOT = Path(__file__).resolve().parents[2]
SHARED = ROOT / "examples/shared/doublet_heat"
OUTPUT = Path(__file__).with_name("module_api_baseline")


def main():
    """Write plant state, full replay, quickstart simulation and timing metadata."""
    OUTPUT.mkdir(exist_ok=True)
    plant = DoubletHeatPlant.load(SHARED / "plant.json")
    data = gm.Dataset.from_frame(
        pd.read_csv(SHARED / "doublet_2024_15min.csv", parse_dates=["time"]),
        time_column="time",
    )

    started = perf_counter()
    replay = gm.Engine().replay(plant, data)
    replay_seconds = perf_counter() - started
    replay.to_frame().to_csv(OUTPUT / "replay.csv.gz", compression="gzip")

    clock = gm.Clock.days(2027, 1, 1, days=1)
    profiles = {
        "production_rate": gm.Profile.constant(150, unit="m3/h", clock=clock),
        "esp_frequency": gm.Profile.constant(55, unit="Hz", clock=clock),
    }
    simulation = gm.Engine().simulate(
        plant, gm.Dataset.from_profiles(profiles), clock=clock
    )
    simulation.to_frame().to_csv(OUTPUT / "simulate.csv.gz", compression="gzip")

    (OUTPUT / "state_dict.json").write_text(
        json.dumps(plant.state_dict(), indent=2, sort_keys=True) + "\n"
    )
    (OUTPUT / "metadata.json").write_text(
        json.dumps(
            {
                "baseline_branch": "refactor",
                "pytest": "148 passed in 288.87s",
                "pytest_wall_seconds": 290.36,
                "replay_rows": len(replay),
                "replay_seconds": replay_seconds,
                "simulate_rows": len(simulation),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"Captured {len(replay)} replay rows in {replay_seconds:.3f} s")


if __name__ == "__main__":
    main()
