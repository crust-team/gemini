"""The profile catalogue and the profile file reader."""

from pathlib import Path

import pandas as pd

from gemini.errors import NotImplementedYet, ValidationError
from gemini.utils.files import read_json
from gemini.utils.strings import close_matches, did_you_mean, join_names

NAMES = ("heating_demand", "cooling_demand")
"""The design-year demand profiles of the heating and cooling challenge."""

DATA = Path(__file__).parent / "data"
KEYS = ("name", "description", "source", "columns", "time", "values")


def names():
    """Return the profile names, in the order heating then cooling."""
    return list(NAMES)


def get(name):
    """Return profile ``name`` as a DataFrame in the run-input format.

    The index is a timezone-aware UTC ``DatetimeIndex`` called ``time``; each column holds one
    quantity in the unit its profile file declares, listed in ``frame.attrs["units"]``. An unknown
    name raises ``ValidationError`` with close matches. A name whose data is not in the package
    raises ``NotImplementedYet`` naming the file to add.
    """
    if name not in NAMES:
        raise ValidationError(
            f"profiles.get: unknown profile {name!r}; valid: {join_names(NAMES)}"
            f"{did_you_mean(name, NAMES)}",
            path=name,
            suggestions=close_matches(name, NAMES),
            code="unknown_name",
        )
    path = DATA / f"{name}.json"
    if not path.exists():
        raise NotImplementedYet(
            f"profiles.get: {name!r} has no data yet; add profiles/data/{name}.json "
            "with the hackathon demand inputs"
        )
    return read(path)


def read(path):
    """Read a profile file into a DataFrame with the units in ``attrs["units"]``."""
    profile = read_json(path)
    missing = [key for key in KEYS if key not in profile]
    if missing:
        raise ValidationError(
            f"{path}: missing keys {join_names(missing)}", path=str(path), code="invalid_format"
        )
    index = pd.DatetimeIndex(pd.to_datetime(profile["time"], utc=True), name="time")
    frame = pd.DataFrame(
        {name: profile["values"][name] for name in profile["columns"]}, index=index
    )
    frame.attrs["units"] = {name: item["unit"] for name, item in profile["columns"].items()}
    return frame
