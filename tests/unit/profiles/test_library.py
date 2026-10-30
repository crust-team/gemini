"""The profile catalogue: names, the missing data and the profile file reader."""

import json

import pandas as pd
import pytest

import gemini as gm
from gemini.profiles import library

PROFILE = {
    "name": "heating_demand",
    "description": "Two hours of a test profile.",
    "source": "written by the test",
    "columns": {"heating_consumer.heat_demand": {"unit": "W", "quantity": "power"}},
    "time": ["2024-01-01T00:00:00Z", "2024-01-01T02:00:00+01:00"],
    "values": {"heating_consumer.heat_demand": [1.5e5, None]},
}


def test_names_are_the_heating_and_cooling_profiles():
    """The public names are fixed and in a stable order."""
    assert gm.profiles.names() == ["heating_demand", "cooling_demand"]


def test_a_profile_without_data_says_which_file_is_missing():
    """No demand data ships, so get raises NotImplementedYet naming the file to add."""
    with pytest.raises(gm.errors.NotImplementedYet, match="profiles/data/cooling_demand.json"):
        gm.profiles.get("cooling_demand")


def test_an_unknown_profile_has_close_matches():
    """A misspelt name carries suggestions."""
    with pytest.raises(gm.errors.UnknownNameError) as unknown:
        gm.profiles.get("heating_demnd")
    assert unknown.value.suggestions[0] == "heating_demand"


def test_a_profile_file_becomes_a_run_input_frame(tmp_path, monkeypatch):
    """The frame has a UTC time index, a column per quantity and its units in attrs."""
    (tmp_path / "heating_demand.json").write_text(json.dumps(PROFILE))
    monkeypatch.setattr(library, "DATA", tmp_path)
    frame = gm.profiles.get("heating_demand")
    assert isinstance(frame.index, pd.DatetimeIndex) and str(frame.index.tz) == "UTC"
    assert frame.index.name == "time" and frame.index[1] == pd.Timestamp("2024-01-01T01:00:00Z")
    assert list(frame.columns) == ["heating_consumer.heat_demand"]
    assert frame.attrs["units"] == {"heating_consumer.heat_demand": "W"}
    assert frame["heating_consumer.heat_demand"].iloc[0] == 1.5e5
    assert pd.isna(frame["heating_consumer.heat_demand"].iloc[1])


def test_a_profile_file_with_missing_keys_is_refused(tmp_path):
    """Every key of the format is required; the error lists the missing ones."""
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"name": "broken"}))
    with pytest.raises(gm.errors.ValidationError, match="columns, time, values"):
        library.read(path)
