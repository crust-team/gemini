"""Plants whose consumers declare a cost, and runs of them, for the economics tests.

The consumers join the plant with ``add_module``, so the test classes stay out of the registry.
"""

import gemini as gm
from gemini.modules import CoolingGrid, ElectricityGrid, GasGrid, HeatingGrid
from gemini.types.cost import Cost
from tests.fixtures.result_tables import make_results

HOURS = 24
"""Ticks of an hour in the runs below."""


class CostedHeatingGrid(HeatingGrid):
    """A heat consumer that declares 1000 EUR, 10 EUR/year fixed and 1e-9 EUR/J variable cost."""

    def capex(self, assumptions):
        """Return the declared cost."""
        return Cost(
            capex=1000.0,
            opex_fixed=10.0,
            opex_variable=1e-9,
            currency="EUR",
            price_year=2024,
            source="test fixture",
        )


class CostedCoolingGrid(CoolingGrid):
    """A cooling consumer that declares 2000 EUR and no running cost."""

    def capex(self, assumptions):
        """Return the declared cost."""
        return Cost(capex=2000.0, currency="EUR", price_year=2024, source="test fixture")


def _with_grids(plant):
    """Add the electricity and gas grids the bills of a run read."""
    plant._add_module("grid", ElectricityGrid())
    plant._add_module("gas", GasGrid())
    return plant


def heating_plant(costed=True):
    """Return a plant with one heat consumer, costed or not."""
    plant = gm.Plant("Heating")
    plant._add_module("heat", CostedHeatingGrid() if costed else HeatingGrid())
    return _with_grids(plant)


def cooling_plant():
    """Return a plant with one costed cooling consumer."""
    plant = gm.Plant("Cooling")
    plant._add_module("cool", CostedCoolingGrid())
    return _with_grids(plant)


def day(heat=1000.0, cold=None, electricity=100.0, generated=None, fuel=None):
    """Return a day of hourly constant powers [W] at the edge modules."""
    sold = generated or 0.0
    columns = {
        "grid": {
            "power_out": [electricity] * HOURS,
            "power_in": [sold] * HOURS,
            "net_import": [max(electricity - sold, 0.0)] * HOURS,
            "net_export": [max(sold - electricity, 0.0)] * HOURS,
        }
    }
    if heat is not None:
        columns["heat"] = {
            "supply_in.enthalpy_flow": [heat] * HOURS,
            "return_out.enthalpy_flow": [0.0] * HOURS,
            "unmet_demand": [0.0] * HOURS,
        }
    if cold is not None:
        columns["cool"] = {
            "supply_in.enthalpy_flow": [0.0] * HOURS,
            "return_out.enthalpy_flow": [cold] * HOURS,
        }
    if fuel is not None:
        columns["gas"] = {"gas_out.chemical_flow": [fuel] * HOURS}
    return make_results(columns)
