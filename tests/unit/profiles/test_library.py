"""The profile catalogue: the organiser demand files read as run input."""

import pandas as pd
import pytest

import gemini as gm
from tests.fixtures.errors import raises

HOURS_PER_DAY = 24


def test_names_are_the_heating_and_cooling_profiles():
    """The public names are fixed and in a stable order."""
    assert gm.profiles.names() == ["heating_demand", "cooling_demand"]


@pytest.mark.parametrize(
    "name, peak_mw, peak_day, energy_gwh, file",
    [
        ("heating_demand", 30.0, "2027-01-28", 111.67, "GEMINI_Heating_Demand_Daily_2027.csv"),
        ("cooling_demand", 10.0, "2027-07-19", 23.74, "GEMINI_Cooling_Demand_Daily_2027.csv"),
    ],
)
def test_the_key_figures_of_the_challenge(name, peak_mw, peak_day, energy_gwh, file):
    """365 UTC days in W with the peak, its date and the annual energy of the challenge text."""
    frame = gm.profiles.get(name)
    assert isinstance(frame.index, pd.DatetimeIndex) and str(frame.index.tz) == "UTC"
    assert frame.index.name == "time" and list(frame.columns) == [name] and len(frame) == 365
    assert frame.index[0] == pd.Timestamp("2027-01-01", tz="UTC")
    assert frame.index[-1] == pd.Timestamp("2027-12-31", tz="UTC")
    assert (frame.index[1:] - frame.index[:-1] == pd.Timedelta(days=1)).all()
    assert frame.attrs["units"] == {name: "W"} and frame.attrs["quantities"] == {name: "power"}
    assert file in frame.attrs["source"]
    assert frame[name].max() == pytest.approx(peak_mw * 1e6)
    assert frame[name].idxmax() == pd.Timestamp(peak_day, tz="UTC")
    assert (frame[name].sum() * HOURS_PER_DAY / 1e9).round(2) == energy_gwh


def test_a_profile_is_a_run_input():
    """A frame of ``get`` is accepted as run input."""
    assert len(gm.Dataset(gm.profiles.get("cooling_demand"))) == 365


def test_an_unknown_profile_has_close_matches():
    """A misspelt name carries suggestions."""
    with raises(gm.errors.ValidationError, "unknown_name") as unknown:
        gm.profiles.get("heating_demnd")
    assert unknown.value.suggestions[0] == "heating_demand"
