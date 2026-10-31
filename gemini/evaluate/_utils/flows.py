"""What a run bought, sold and discarded over a year, and what it cost or earned."""

import numpy as np

from gemini.errors import ValidationError
from gemini.evaluate._utils.series import (
    edge_total,
    energy,
    useful_cold,
    useful_heat,
    window_seconds,
)
from gemini.modules.grids import ChemicalGrid, ElectricityGrid, GasGrid, WasteGrid
from gemini.units import SECONDS_PER_YEAR

CARRIERS = {
    "heat": "heat",
    "cold": "cold",
    "electricity": "electricity",
    "fuel": "gas",
    "waste": "waste_disposal",
    "chemical": "chemical",
}
"""Each flow of ``Flows`` with the carrier whose price it takes."""


class Flows:
    """The powers at the edge of a plant over a run: heat, cold, electricity, fuel and the rest.

    The run is taken as representative of a year: ``energy`` scales the joules or kilograms of the
    window by one year over that window. Everything is read from the ports of the edge modules; a
    plant without such a module has none of it. A tick without a value adds nothing.
    """

    def __init__(self, plant, results):
        """Read the series of the six flows from the finished run ``results``."""
        frame = results.to_frame()
        self.seconds = window_seconds(results)
        self.scale = SECONDS_PER_YEAR / self.seconds.sum()
        self.series = {
            "heat": useful_heat(plant, frame),
            "cold": useful_cold(plant, frame),
            "electricity": edge_total(plant, frame, "net_import", ElectricityGrid),
            "fuel": edge_total(plant, frame, "gas_out.chemical_flow", GasGrid),
            "waste": edge_total(plant, frame, "waste_in.mass_flow", WasteGrid),
            "chemical": edge_total(plant, frame, "chemical_out.mass_flow", ChemicalGrid),
        }

    def energy(self, name):
        """Return the amount of ``name`` per year [J, kg]; zero when the plant lacks it."""
        series = self.series[name]
        return 0.0 if series is None else energy(series, self.seconds) * self.scale

    def cost(self, name, problem):
        """Return the yearly money of ``name`` at the price of its carrier, zero when none flows.

        A price that is a number multiplies the amount of the year. A price along the demand
        multiplies the power of each step: the bill is the sum over the steps of power, duration
        and price, scaled to a year. A carrier that flows without a price raises
        ``missing_assumption``.
        """
        if self.energy(name) <= 0:
            return 0.0
        price = problem.assumptions.price(CARRIERS[name])
        if np.ndim(price) == 0:
            return self.energy(name) * float(price)
        if len(price) != len(self.seconds):
            raise ValidationError(
                f"price of {CARRIERS[name]} has {len(price)} values; expected {len(self.seconds)}, "
                "one per step of the run",
                path=f"assumptions.prices.{CARRIERS[name]}",
                code="invalid_value",
            )
        power = self.series[name].to_numpy(dtype=float)
        return float(np.nansum(power * self.seconds * price)) * self.scale
