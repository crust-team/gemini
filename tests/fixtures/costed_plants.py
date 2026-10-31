"""Plants whose consumers declare a cost, and runs of them, for the economics tests.

The consumers join the plant with ``add_module``, so the test classes stay out of the registry.
"""

import gemini as gm
from gemini.modules import CoolingConsumer, HeatConsumer
from gemini.types.cost import Cost
from tests.fixtures.result_tables import make_results

HOURS = 24
"""Ticks of an hour in the runs below."""


class CostedHeatConsumer(HeatConsumer):
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


class CostedCoolingConsumer(CoolingConsumer):
    """A cooling consumer that declares 2000 EUR and no running cost."""

    def capex(self, assumptions):
        """Return the declared cost."""
        return Cost(capex=2000.0, currency="EUR", price_year=2024, source="test fixture")


def heating_plant(costed=True):
    """Return a plant with one heat consumer, costed or not."""
    plant = gm.Plant("Heating")
    plant.add_module("heat", CostedHeatConsumer() if costed else HeatConsumer())
    return plant


def cooling_plant():
    """Return a plant with one costed cooling consumer."""
    plant = gm.Plant("Cooling")
    plant.add_module("cool", CostedCoolingConsumer())
    return plant


def day(heat=1000.0, cold=None, electricity=100.0, generated=None, fuel=None):
    """Return a day of hourly constant powers [W] of the named leaves."""
    columns = {"pump": {"electricity": [electricity] * HOURS}}
    if heat is not None:
        columns["heat"] = {"heat_supplied": [heat] * HOURS, "unmet_demand": [0.0] * HOURS}
    if cold is not None:
        columns["cool"] = {"heat_absorbed": [cold] * HOURS}
    if generated is not None:
        columns["chp"] = {"electricity_generated": [generated] * HOURS}
    if fuel is not None:
        columns["boiler"] = {"fuel": [fuel] * HOURS}
    return make_results(columns)
