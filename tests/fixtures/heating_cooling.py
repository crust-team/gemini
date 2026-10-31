"""The heating and cooling plants of ``inputs/plants/`` and two days of their demand.

The values are the challenge's, or the sizes the example files state as assumptions. The days are
round numbers every plant covers.
"""

import pandas as pd

import gemini as gm

HEAT = 12e6
"""Heating demand of the days [W]."""
COLD = 5e6
"""Cooling demand of the days [W]."""
RULES = {"doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"}, "max_brine_cooling": "40 K"}


def filled_dict(name):
    """Return the plant dict of plant class ``name`` with the values of its example."""
    return gm.plants.example(name).to_dict(structure=True)


def two_days():
    """Return two days of demand [W]."""
    index = pd.date_range("2027-07-01", periods=2, freq="D", tz="UTC", name="time")
    return pd.DataFrame({"heating_demand": HEAT, "cooling_demand": COLD}, index=index)
