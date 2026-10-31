"""The hackathon case: two doublets, heat exchanger, heat pump, gas boiler and absorption chiller.

Schedules 2027 from the daily demand on ``gm.plants.example("HackathonPlant")`` and simulates it.
The reservoir, brine, limits and supply temperatures are the challenge's; what this case assumes
it prints as assumptions. Shows ``gm.schedule``, ``gm.simulate``, ``gm.checks.limits``,
``gm.checks.plant_balance``, ``gm.kpi.totals``, ``gm.kpi.compute`` and ``gm.economics``.

Run with ``python examples/cases/hackathon.py``.
"""

import pandas as pd

import gemini as gm

MWH = 1000 * gm.units.convert(1, "kWh", "J")
GWH = 1000 * MWH
INPUTS = {
    "heat_pump.temperature_setpoint": "100 degC",
    "boiler.temperature_setpoint": "100 degC",
    "chiller.temperature_setpoint": "20 degC",
    "cool_users.indoor_temperature": "26 degC",
    "cool_users.indoor_relative_humidity": 0.5,
    "chiller_cooler.temperature_setpoint": "15 degC",
    "chiller_cooler.flow": "800 kg/s",
    "air.temperature": "10 degC",
    "desander.sand_concentration": "20 mg/l",
    "dosing.dose": "10 ppm",
}
RULES = {
    "order": ["geothermal", "heat_pump", "boiler"],
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": None,
}
PRICES = dict(
    discount_rate=0.05,
    lifetime_years=25,
    electricity_price=100.0 / MWH,
    gas_price=40.0,
    heat_price=60.0 / MWH,
    cold_price=60.0 / MWH,
    electricity_emission_factor=0.3 / gm.units.convert(1, "kWh", "J"),
    pump_cost=0.5,
    chiller_cost=0.3,
    exchanger_cost=0.5,
    flare_cost=1e5,
    makeup_cost=5e4,
    waste_disposal_price=0.2,
    chemical_price=3.0,
)
"""Placeholders, not data: the prices and the factors without a source are this case's."""

ASSUMPTIONS = """Assumptions of this case, not of the challenge:
  heating return 60 °C, cooling return 25 °C, chiller cooling water 15 °C
  air 10 °C; the chiller's dry cooler: 5 K approach, 2 % fan power
  20 mg/l sand, 90 % desander, 10 ppm inhibitor
  heat exchanger, heat pump, boiler and chiller sizes; 1000 m drainage radius
  discount rate, lifetime, every price and the cost factors without a source"""


def hackathon_limits():
    """Return the hard limits of the challenge."""
    limits = gm.checks.Limits()
    limits.add("d*.flow", min="50 m3/h", max="300 m3/h")
    limits.add("d*.brine_cooling", max="40 K")
    limits.add("boiler.fluid_out.temperature", min="100 degC")
    return limits


def print_run(plant, results):
    """Print the delivered energy, what remained unmet and the peaks, for daily steps."""
    frame = results.to_frame()
    gwh = 24.0 / 1e9
    gas = frame["gas_grid.gas_out.chemical_flow"]
    totals = gm.kpi.totals(plant, results)
    boiler = frame["boiler.fluid_out.enthalpy_flow"] - frame["boiler.fluid_in.enthalpy_flow"]
    sink = frame["heat_pump.sink_out.enthalpy_flow"] - frame["heat_pump.sink_in.enthalpy_flow"]
    rows = (
        ("heat delivered", totals["heat_delivered"]["value"] / GWH, "GWh"),
        ("heat unmet", frame["heat_users.unmet_demand"].sum() * gwh, "GWh"),
        ("cold delivered", totals["cold_delivered"]["value"] / GWH, "GWh"),
        ("cold unmet", frame["cool_users.unmet_sensible"].sum() * gwh, "GWh"),
        ("boiler, peak", boiler.max() / 1e6, "MW"),
        ("heat pump, peak", sink.max() / 1e6, "MW"),
        ("gas co-produced", (frame["boiler.fuel"] - gas).sum() * gwh, "GWh burnt"),
        ("gas purchased", gas.sum() * gwh, "GWh"),
        ("supply, lowest", frame["boiler.fluid_out.temperature"].min() - 273.15, "°C"),
    )
    print("\nThe year, in daily steps:")
    for label, value, unit in rows:
        print(f"  {label:<17} {value:8.2f} {unit}")


def print_limits(checks):
    """Print each limit of the challenge, in the units of the challenge."""
    print("\nLimits:")
    for item in checks:
        value, unit = item["value"]["value"], item["value"]["unit"]
        if unit == "m3/s":
            value, unit = gm.units.convert(value, unit, "m3/h"), "m³/h"
        if item["name"].endswith("temperature"):
            value, unit = gm.units.convert(value, unit, "degC"), "°C"
        result = "ok" if item["passed"] else "VIOLATED"
        print(f"  {item['name']:<28} {result:<9} worst {value:.4g} {unit}")


def print_balance(checks):
    """Print the plant balance: the root, and how many modules close."""
    modules = [item for item in checks if not item["name"].startswith("plant ")]
    closed = sum(item["passed"] is True for item in modules)
    print(f"\nBalance:\n  modules that close {closed} of {len(modules)}")
    for item in checks[-2:]:
        result = "ok" if item["passed"] else "OPEN"
        print(f"  {item['name']:<18} {result:<5} worst {item['value']['value']:.3g}")


def print_totals(plant, results):
    """Print what crossed the plant's edge and the KPIs of the run."""
    print("\nAt the plant's edge:")
    for name, item in gm.kpi.totals(plant, results).items():
        scale, unit = (GWH, "GWh") if item["unit"] == "J" else (1e6, "kt")
        print(f"  {name:<20} {item['value'] / scale:10.3f} {unit}")
    print("\nKPIs:")
    for name, item in gm.kpi.compute(plant, results).items():
        scale, unit = (1e6, "MW") if item["unit"] == "W" else (1, "")
        print(f"  {name:<18} {item['value'] / scale:.4g} {unit}".rstrip())


def print_economics(plant, results):
    """Print the economics in the units people read; every price is a placeholder."""
    totals = gm.kpi.totals(plant, results)
    heat, cold = totals["heat_delivered"]["value"], totals["cold_delivered"]["value"]
    values = gm.economics.Assumptions(heat_cost_share=heat / (heat + cold), **PRICES)
    capex = gm.economics.capex(plant, values)
    rows = (
        ("capex", capex["value"] / 1e6, f"MEUR ({capex['price_year']['value']})"),
        ("opex", gm.economics.opex(plant, results, values)["value"] / 1e6, "MEUR/year"),
        ("CO2-eq", gm.economics.co2(plant, results, values)["value"] / 1e6, "kt/year"),
        ("LCOH", gm.economics.lcoh(plant, results, assumptions=values)["value"] * MWH, "EUR/MWh"),
        ("LCOC", gm.economics.lcoc(plant, results, assumptions=values)["value"] * MWH, "EUR/MWh"),
        ("NPV", gm.economics.npv(plant, results, assumptions=values)["value"] / 1e6, "MEUR"),
        ("payback", gm.economics.payback(plant, results, values)["value"], "years"),
    )
    print("\nEconomics, on the placeholder prices above:")
    for label, value, unit in rows:
        print(f"  {label:<8} {value:8.2f} {unit}")


def main():
    """Plan and simulate the year, then print what it delivered and what it costs."""
    plant = gm.plants.example("HackathonPlant")
    plant.set_inputs(INPUTS)
    profiles = [gm.profiles.get("heating_demand"), gm.profiles.get("cooling_demand")]
    print(ASSUMPTIONS)
    results = gm.simulate(plant, gm.schedule(plant, pd.concat(profiles, axis=1), RULES))
    print_run(plant, results)
    print_limits(gm.checks.limits(plant, results, hackathon_limits()))
    print_balance(gm.checks.plant_balance(plant, results))
    print_totals(plant, results)
    print_economics(plant, results)


if __name__ == "__main__":
    main()
