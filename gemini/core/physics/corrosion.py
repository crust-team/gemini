"""Corrosion integration salvaged from the WIMS production-data workflow."""

import numpy as np


def wall_loss(rates_mm_per_year, durations_s):
    """Return cumulative wall loss [mm] from interval rates [mm/year] and durations [s]."""
    return np.cumsum(np.asarray(rates_mm_per_year) * np.asarray(durations_s) / (365.25 * 24 * 3600))
