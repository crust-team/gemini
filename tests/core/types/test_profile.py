"""Profile time semantics, physical-unit conversion and aggregation."""

from datetime import datetime, timedelta, timezone

import pytest

from gemini.core.types.profile import Profile


def test_csv_previous_and_resample(tmp_path):
    """Read raw temperatures, hold previous samples and aggregate without silent gap filling."""
    path = tmp_path / "input.csv"
    path.write_text("Timestamp;ambient\n2024-01-01 00:00;10\n2024-01-01 01:00;20\n")
    profile = Profile.from_csv(path, "ambient", "degC", tz="Europe/Oslo")
    assert profile.unit == "K" and profile.quantity == "temperature"
    assert profile.values == [283.15, 293.15]
    assert profile.index[0].hour == 23
    assert profile.at(profile.index[0] + timedelta(minutes=30)) == 283.15
    assert profile.at(profile.index[-1] + timedelta(days=1)) == 293.15
    with pytest.raises(ValueError, match="precedes"):
        profile.at(profile.index[0] - timedelta(seconds=1))
    series = profile.to_series()
    series.iloc[0] = 0
    assert profile.values[0] == 283.15
    constant = Profile.constant(
        "load", "power", "W", 10, datetime(2024, 1, 1), 4, timedelta(hours=1)
    )
    assert len(constant.resample(timedelta(hours=2), "mean")) == 2
    assert constant.resample(timedelta(hours=2), "sum").values == [20, 20]
    assert constant.resample(timedelta(hours=2), "first").values == [10, 10]
    for index, values in (
        (profile.index[::-1], profile.values),
        ([profile.index[0]] * 2, [1, 2]),
        (profile.index, [1]),
    ):
        with pytest.raises(ValueError):
            Profile(name="bad", quantity="power", unit="W", index=index, values=values)


def test_profiles_drive_scenario():
    """Dotted profile inputs drive an ordinary handwritten module without configuration."""
    from gemini.core.modes.scenario import run
    from gemini.core.modules.heat.boiler import Boiler

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    target = Profile.constant("target", "temperature", "K", 320, start, 3, timedelta(hours=1))
    inlet = dict(m_dot=1, T=300, p=1e5)
    boiler = Boiler(dict(fuel="electric", capacity=1e6, efficiency=0.9))
    result = run(boiler, {"setpoint_T": target}, 3600, base_inputs={"streams_in": {"inlet": inlet}})
    assert len(result) == 3
    assert result.to_frame()["", "outlet_T"].tolist() == [320] * 3
