"""The public quickstart acceptance path."""

import pandas as pd
import pytest

import gemini as gm

pytestmark = pytest.mark.e2e


def test_quickstart(tmp_path, monkeypatch, dataset_path):
    """Run the quickstart calls against the committed shared example.

    The body is one end-to-end path through the public API, so it stays one function.
    """
    monkeypatch.chdir(tmp_path)

    plant = gm.plants.example("DoubletHeatPlant")
    print(plant)

    df = pd.read_csv(dataset_path, parse_dates=["time"])
    data = gm.Dataset.from_frame(df, time_column="time")

    res = gm.replay(plant, data, checkpoint="runs/replay.ckpt")
    print(res.to_frame(table="energy"))
    esp_power = res["doublet.esp"].power
    assert len(esp_power) == len(df)

    res2 = gm.resume("runs/replay.ckpt")

    fit = gm.analysis.calibrate(
        plant, data, params=[plant.get("heat_exchanger.thermal_conductance")]
    )
    print(fit)
    plant.to_json("runs/my_plant.json")
    assert gm.Plant.from_json("runs/my_plant.json").state_dict() == plant.state_dict()

    clock = gm.engine.Clock.days(2027, 1, 1, days=1)
    profiles = {
        "doublet.reservoir.production_rate": gm.types.Profile.constant(
            150, unit="m3/h", clock=clock
        ),
        "doublet.esp.frequency": gm.types.Profile.constant(55, unit="Hz", clock=clock),
        "injection_pump.pressure_setpoint": gm.types.Profile.constant(
            51.5, unit="bar", clock=clock
        ),
    }
    sim = gm.simulate(plant, plan=gm.Dataset.from_profiles(profiles), clock=clock)
    print(sim.to_frame(table="energy"))

    start = df["time"].iloc[0]
    second = start + pd.Timedelta(days=1)
    third = start + pd.Timedelta(days=2)
    day1 = df[df["time"] < second]
    day2 = df[(df["time"] >= second) & (df["time"] < third)]
    out1 = gm.live(
        plant, gm.Dataset.from_frame(day1, time_column="time"), "runs/live.ckpt", now=second
    )
    out2 = gm.live(
        plant, gm.Dataset.from_frame(day2, time_column="time"), "runs/live.ckpt", now=third
    )
    assert len(res) == len(res2) == len(df)
    assert len(sim) == 24
    assert len(out1) == len(day1) and len(out2) == len(day2)
