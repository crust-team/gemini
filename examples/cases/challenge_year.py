"""The challenge year on the example plant: every requirement, checked on the run.

Plans 2027 for ``gm.plants.example("HeatingCoolingPlant")``, two doublets with a heat pump, a boiler
and three chillers, and simulates it. The reservoir, the brine, the limits and the supply
temperatures are the challenge's; what this case assumes it prints as assumptions.

Shows ``gm.plants.example``, ``gm.schedule``, ``gm.simulate``, ``gm.checks.limits``,
``gm.checks.operating_days``, ``gm.kpi.totals`` and ``gm.economics.lcts``.

Run with ``python examples/cases/challenge_year.py``.
"""

import pandas as pd

import gemini as gm

MWH = 1000 * gm.units.convert(1, "kWh", "J")
GWH = 1000 * MWH
OPERATING_DAYS = 330
RULES = {
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": OPERATING_DAYS,
}
PRICES = dict(
    discount_rate=0.05,
    lifetime_years=25,
    electricity_price=100.0 / MWH,
    gas_price=40.0,
    pump_cost=0.5,
    chiller_cost=0.3,
    exchanger_cost=0.5,
    flare_cost=1e5,
    makeup_cost=5e4,
)
"""Placeholders, not data: the prices and the factors without a source are this case's."""

ASSUMPTIONS = """Assumptions of this case, not of the challenge:
  heating return 60 °C, cooling return 25 °C, air 10 °C all year
  well diameter 244 mm, 1000 m drainage radius, 30 bar at the injection pump
  heat exchanger, heat pump (15 MW), boiler (30 MW), absorption (7 MW), adsorption (1 MW) and
  compression (5 MW) sizes, in inputs/plants/HeatingCoolingPlant.json
  discount rate, lifetime, every price and the cost factors without a source"""


def demand():
    """Return the heating and cooling demand of 2027."""
    return pd.concat([gm.profiles.get(name) for name in gm.profiles.names()], axis=1)


def requirements():
    """Return the limits of the challenge."""
    limits = gm.checks.Limits()
    limits.add("d*.reservoir.liquid_flow", min="50 m3/h", max="300 m3/h")
    limits.add("d*.brine_cooling", max="40 K")
    limits.add("d*.pump_efficiency", min=0.7, max=0.7)
    limits.add("d*.volume_imbalance", min="-1e-6 m3/s", max="1e-6 m3/s")
    limits.add("heating_consumer.supply_in.temperature", min="100 degC")
    limits.add("cooling_consumer.supply_in.temperature", max="20 degC")
    return limits


def print_year(plant, results):
    """Print the energy of the year and the supply temperatures, in daily steps."""
    totals = gm.kpi.totals(plant, results)
    frame = results.to_frame()
    boiler = frame["peak_boiler.fluid_out.enthalpy_flow"]
    boiler = boiler - frame["peak_boiler.fluid_in.enthalpy_flow"]
    cold = frame["cooling_consumer.supply_in.mass_flow"] > 0
    rows = (
        ("heat delivered", totals["heat_delivered"]["value"] / GWH, "GWh"),
        ("heat useful", totals["heat_useful"]["value"] / GWH, "GWh"),
        ("heat surplus", totals["heat_surplus"]["value"] / GWH, "GWh"),
        ("heat unmet", frame["heating_consumer.unmet_demand"].sum() * 86400 / GWH, "GWh"),
        ("cold delivered", totals["cold_delivered"]["value"] / GWH, "GWh"),
        ("cold useful", totals["cold_useful"]["value"] / GWH, "GWh"),
        ("cold surplus", totals["cold_surplus"]["value"] / GWH, "GWh"),
        ("cold unmet", frame["cooling_consumer.unmet_sensible"].sum() * 86400 / GWH, "GWh"),
        ("boiler", boiler.sum() * 86400 / GWH, "GWh"),
        ("boiler, peak", boiler.max() / 1e6, "MW"),
        ("electricity", totals["electricity_bought"]["value"] / GWH, "GWh"),
        ("gas bought", totals["gas_bought"]["value"] / GWH, "GWh"),
        (
            "heating supply",
            frame["heating_consumer.supply_in.temperature"].min() - 273.15,
            "°C, lowest",
        ),
        (
            "cooling supply",
            frame["cooling_consumer.supply_in.temperature"][cold].max() - 273.15,
            "°C, warmest",
        ),
    )
    print("\nThe year, in daily steps:")
    for label, value, unit in rows:
        print(f"  {label:<15} {value:8.2f} {unit}")


def print_checks(checks):
    """Print each requirement: its verdict and the worst value of the run."""
    print("\nRequirements:")
    for item in checks:
        result = "ok" if item["passed"] else "VIOLATED"
        worst, unit = item["value"]["value"], item["value"]["unit"]
        if unit == "m3/s" and "flow" in item["name"]:
            worst, unit = gm.units.convert(worst, unit, "m3/h"), "m³/h"
        if unit == "K" and item["name"].endswith("temperature"):
            worst, unit = gm.units.convert(worst, unit, "degC"), "°C"
        print(f"  {item['name']:<39} {result:<9} worst {worst:.4g} {unit}")


def main():
    """Plan and simulate the year, then print what it delivered and each requirement."""
    plant = gm.plants.example("HeatingCoolingPlant")
    print(ASSUMPTIONS)
    results = gm.simulate(plant, gm.schedule(plant, demand(), RULES), on_error="record")
    print(f"\nFailed days: {len(results.errors())}")
    print_year(plant, results)
    days = gm.checks.operating_days(plant, results, OPERATING_DAYS)
    print_checks(gm.checks.limits(plant, results, requirements()) + days)
    lcts = gm.economics.lcts(plant, results, assumptions=gm.economics.Assumptions(**PRICES))
    print(f"\nLCTS, on the placeholder prices above: {lcts['value'] * MWH:.2f} EUR/MWh")


if __name__ == "__main__":
    main()
