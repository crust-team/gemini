"""The demand year on a sample plant: every requirement, checked on the run.

Plans 2027 for the plant dict ``plant.json`` of the sample problem, two doublets with a heat pump,
a boiler and three chillers, and simulates it. The reservoir, the brine, the limits and the supply
temperatures are the sample problem's; what this case assumes it prints as assumptions.

Shows ``gm.plants.from_dict``, ``gm.profiles.from_csv``, ``gm.schedule``, ``gm.simulate``,
``gm.checks.Limits.from_dict``, ``gm.checks.limits``, ``gm.checks.operating_time``,
``gm.kpi.totals`` and ``gm.economics.lcts``.

Run with ``python examples/cases/challenge_year.py``.
"""

import json
from pathlib import Path

import pandas as pd

import gemini as gm

MWH = 1000 * gm.units.convert(1, "kWh", "J")
GWH = 1000 * MWH
SAMPLE = Path(__file__).resolve().parents[2] / "inputs/examples/hackathon_2027"
"""The sample problem, read by this example only."""
HEATING_FILE = "GEMINI_Heating_Demand_Daily_2027.csv"
COOLING_FILE = "GEMINI_Cooling_Demand_Daily_2027.csv"


def sample(name):
    """Return the JSON file ``name`` of the sample problem as data."""
    return json.loads((SAMPLE / name).read_text())


def demand():
    """Return the heating and cooling demand of the two files of the sample problem."""
    heat = {"heating_demand_MWth": "heating_demand"}
    cool = {"cooling_demand_MWcool": "cooling_demand"}
    return pd.concat(
        [
            gm.profiles.from_csv(SAMPLE / HEATING_FILE, heat, "MW", time_column="date"),
            gm.profiles.from_csv(SAMPLE / COOLING_FILE, cool, "MW", time_column="date"),
        ],
        axis=1,
    )


ASSUMPTIONS = """Assumptions of this case, not of the sample problem:
  heating return 60 °C, cooling return 25 °C, air 10 °C all year
  well diameter 244 mm, 1000 m drainage radius, 30 bar at the injection pump
  heat exchanger, heat pump (15 MW), boiler (30 MW), absorption (7 MW), adsorption (1 MW) and
  compression (5 MW) sizes, in plant.json of the sample problem
  discount rate, lifetime, every price and the cost factors without a source"""


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
        if unit == "s":
            worst, unit = worst / 86400, "day"
        print(f"  {item['name']:<39} {result:<9} worst {worst:.4g} {unit}")


def main():
    """Plan and simulate the year, then print what it delivered and each requirement."""
    plant = gm.plants.from_dict(sample("plant.json"))
    print(ASSUMPTIONS)
    rules = sample("rules.json")
    plan = gm.schedule(plant, demand(), rules)
    results = gm.simulate(plant, plan, on_error="record")
    print(f"\nFailed days: {len(results.errors())}")
    print_year(plant, results)
    requirements = gm.checks.Limits.from_dict(sample("limits.json"))
    times = gm.checks.operating_time(plant, results, rules["operating_time"])
    print_checks(gm.checks.limits(plant, results, requirements) + times)
    lcts = gm.economics.lcts(
        plant, results, assumptions=gm.economics.Assumptions(**sample("assumptions.json"))
    )
    print(f"\nLCTS, on the placeholder prices above: {lcts['value'] * MWH:.2f} EUR/MWh")


if __name__ == "__main__":
    main()
