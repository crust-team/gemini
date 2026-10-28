"""The complete public quickstart acceptance path."""

from pathlib import Path

import pandas as pd
import pytest

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

pytestmark = pytest.mark.e2e


def test_quickstart(tmp_path, monkeypatch):
    """Run the documented calls unchanged against the committed shared example."""
    root = Path(__file__).parents[2]
    (tmp_path / "examples").symlink_to(root / "examples", target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    SHARED = "examples/shared/doublet_heat"

    plant = DoubletHeatPlant.load(f"{SHARED}/plant.json")
    print(plant)

    df = pd.read_csv(f"{SHARED}/doublet_2024_15min.csv", parse_dates=["time"])
    data = gm.Dataset.from_frame(df, time_column="time")

    engine = gm.Engine()
    res = engine.replay(plant, data)
    print(res.summary())
    esp_power = res["doublet.esp"].power
    assert len(esp_power) == len(df)

    engine.save_checkpoint("runs/replay.ckpt")
    engine2 = gm.Engine.load_checkpoint("runs/replay.ckpt")
    res2 = engine2.resume()

    fit = gm.optim.calibrate(plant, data, params=[plant.get_parameter("heat_exchanger.ua")])
    print(fit)
    plant.save("runs/my_plant.json")
    assert DoubletHeatPlant.load("runs/my_plant.json").state_dict() == plant.state_dict()

    clock = gm.Clock.days(2027, 1, 1, days=1)
    profiles = {
        "production_rate": gm.Profile.constant(150, unit="m3/h", clock=clock),
        "esp_frequency": gm.Profile.constant(55, unit="Hz", clock=clock),
    }
    sim = engine.simulate(plant, gm.Dataset.from_profiles(profiles), clock=clock)
    print(sim.summary())

    day1 = df[df["time"] < "2024-06-08"]
    day2 = df[(df["time"] >= "2024-06-08") & (df["time"] < "2024-06-09")]
    out1 = engine.live(
        plant,
        gm.Dataset.from_frame(day1, time_column="time"),
        checkpoint="runs/live.ckpt",
        now="2024-06-08T00:00:00Z",
    )
    out2 = engine.live(
        plant,
        gm.Dataset.from_frame(day2, time_column="time"),
        checkpoint="runs/live.ckpt",
        now="2024-06-09T00:00:00Z",
    )
    assert len(res) == len(res2) == 17280
    assert len(sim) == 24
    assert len(out1) == len(out2) == 96
