"""The public quickstart acceptance path."""

import pandas as pd
import pytest

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant
from tests.fixtures import ROOT

pytestmark = pytest.mark.e2e


def test_quickstart(tmp_path, monkeypatch, dataset_path):
    """Run the quickstart calls against the committed shared example.

    The body is one end-to-end path through the public API, so it stays one function.
    """
    (tmp_path / "examples").symlink_to(ROOT / "examples", target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    SHARED = "examples/shared/doublet_heat"

    plant = DoubletHeatPlant.load(f"{SHARED}/plant.json")
    print(plant)

    df = pd.read_csv(dataset_path, parse_dates=["time"])
    data = gm.Dataset.from_frame(df, time_column="time")

    engine = gm.Engine(plant)
    res = engine.replay(data)
    print(res.energy_report())
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
        "doublet.reservoir.production_rate": gm.Profile.constant(150, unit="m3/h", clock=clock),
        "doublet.esp.frequency": gm.Profile.constant(55, unit="Hz", clock=clock),
        "injection_pump.pressure_setpoint": gm.Profile.constant(51.5, unit="bar", clock=clock),
    }
    sim = engine.simulate(gm.Dataset.from_profiles(profiles), clock=clock)
    print(sim.energy_report())

    start = df["time"].iloc[0]
    second = start + pd.Timedelta(days=1)
    third = start + pd.Timedelta(days=2)
    day1 = df[df["time"] < second]
    day2 = df[(df["time"] >= second) & (df["time"] < third)]
    out1 = engine.live(
        gm.Dataset.from_frame(day1, time_column="time"),
        checkpoint="runs/live.ckpt",
        now=second,
    )
    out2 = engine.live(
        gm.Dataset.from_frame(day2, time_column="time"),
        checkpoint="runs/live.ckpt",
        now=third,
    )
    assert len(res) == len(res2) == len(df)
    assert len(sim) == 24
    assert len(out1) == len(day1) and len(out2) == len(day2)
