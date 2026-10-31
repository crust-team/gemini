"""The profile catalogue: the organisers' demand files, read as run input."""

import pandas as pd

from gemini.errors import ValidationError
from gemini.physics import units
from gemini.utils import paths
from gemini.utils.strings import close_matches, did_you_mean, join_names

SOURCE = "GEMINI Hackathon challenge requirements, 28 October 2026, section 2"
SI_UNIT = "W"

PROFILES = {
    "heating_demand": {
        "file": "GEMINI_Heating_Demand_Daily_2027.csv",
        "column": "heating_demand_MWth",
        "unit": "MW",
        "quantity": "power",
        "description": "Daily-average heating demand of 2027: peak 30.0 MWth, 111.67 GWh/year.",
    },
    "cooling_demand": {
        "file": "GEMINI_Cooling_Demand_Daily_2027.csv",
        "column": "cooling_demand_MWcool",
        "unit": "MW",
        "quantity": "power",
        "description": "Daily-average cooling demand of 2027: peak 10.0 MWcool, 23.74 GWh/year.",
    },
}
"""Name, file, unit and description of each profile; the files are the organisers', unchanged."""


def names():
    """Return the profile names, in the order heating then cooling."""
    return list(PROFILES)


def get(name):
    """Return profile ``name`` as a DataFrame in the run-input format.

    The index is a timezone-aware UTC ``DatetimeIndex`` called ``time``, one row per day of the
    file. The one column is called ``name`` and holds the daily-average demand in W. ``attrs`` has
    ``units``, ``quantities``, ``description`` and ``source``, which names the organiser file. An
    unknown name raises ``ValidationError`` with close matches, and without ``inputs/`` of a source
    checkout this raises ``inputs_missing``.
    """
    if name not in PROFILES:
        raise ValidationError(
            f"profiles.get: unknown profile {name!r}; valid: {join_names(PROFILES)}"
            f"{did_you_mean(name, PROFILES)}",
            path=name,
            suggestions=close_matches(name, PROFILES),
            code="unknown_name",
        )
    profile = PROFILES[name]
    data = pd.read_csv(paths.hackathon(profile["file"]))
    index = pd.DatetimeIndex(pd.to_datetime(data["date"], utc=True), name="time")
    values = units.array_convert(data[profile["column"]], profile["unit"], SI_UNIT)
    frame = pd.DataFrame({name: values}, index=index)
    frame.attrs["units"] = {name: SI_UNIT}
    frame.attrs["quantities"] = {name: profile["quantity"]}
    frame.attrs["description"] = profile["description"]
    frame.attrs["source"] = f"{profile['file']}, {SOURCE}"
    return frame
