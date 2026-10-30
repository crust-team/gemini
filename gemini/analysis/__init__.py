"""Well performance, well integrity and the plant KPIs."""

from gemini.analysis.fits import (
    estimate_conductance,
    estimate_reservoir_pressure,
    fit_head_coefficients,
    fit_head_correction,
)
from gemini.analysis.integrity import (
    calibrate_corrosion,
    corrosion_forecast,
    erosion,
)
from gemini.analysis.wells import calibrate_pump, injectivity, nodal, pump_curve

__all__ = [
    "nodal",
    "injectivity",
    "pump_curve",
    "calibrate_pump",
    "calibrate_corrosion",
    "corrosion_forecast",
    "erosion",
    "fit_head_coefficients",
    "fit_head_correction",
    "estimate_reservoir_pressure",
    "estimate_conductance",
]
