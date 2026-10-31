"""Price a small plant: investment, yearly cost, levelised cost of heat and CO2.

Shows ``gm.economics.Assumptions``, ``capex``, ``opex``, ``lcoh`` and ``co2`` on a boiler that
serves a heating grid. Every price is an assumption of this recipe, not data, and it prints them.

Run with ``python examples/recipes/economics.py``.
"""

import gemini as gm

MWH = 1000 * gm.units.convert(1, "kWh", "J")
DAY = gm.Clock.days(2027, 1, 1, days=1)
INPUTS = {
    "users.heat_demand": (500, "kW"),
    "users.flow": (15, "kg/s"),
    "boiler.temperature_setpoint": (90, "degC"),
}
ASSUMPTIONS = gm.economics.Assumptions(
    discount_rate=0.05, lifetime_years=25, gas_price=40.0, heat_price=60.0 / MWH
)


def build():
    """Return a boiler on a heating grid, with its gas from a grid and its flue to the air."""
    plant = gm.Plant("BoilerPlant")
    users = {"return_temperature": "60 degC", "return_pressure": "6 bar"}
    plant.add("HeatingGrid", name="users", params=users)
    plant.add("Boiler", name="boiler", params={"capacity": "1 MW", "efficiency": 0.9})
    plant.add("GasGrid", name="gas")
    plant.add("Atmosphere", name="air")
    plant.connect("users.return_out", "boiler.fluid_in")
    plant.connect("boiler.fluid_out", "users.supply_in")
    plant.connect("gas.gas_out", "boiler.fuel_in")
    plant.connect("boiler.flue_out", "air.gas_in")
    plant.connect("boiler.loss_out", "air.heat_in")
    plant.air.temperature = "10 degC"
    return plant


def main():
    """Simulate a representative day and print the economics of a year."""
    print("Assumptions: 5 % discount rate, 25 years, gas at 40 EUR/MWh, heat at 60 EUR/MWh")
    profiles = {
        path: gm.Profile.constant(value, unit=unit, clock=DAY)
        for path, (value, unit) in INPUTS.items()
    }
    plant = build()
    results = gm.simulate(plant, gm.Dataset.from_profiles(profiles), clock=DAY)
    investment = gm.economics.capex(plant, ASSUMPTIONS)
    yearly = gm.economics.opex(plant, results, ASSUMPTIONS)
    heat = gm.economics.lcoh(plant, results, assumptions=ASSUMPTIONS)
    emitted = gm.economics.co2(plant, results, ASSUMPTIONS)
    prices = investment["price_year"]["value"]
    print(f"Capex:  {investment['value'] / 1e3:8.1f} kEUR, prices of {prices}")
    print(f"Opex:   {yearly['value'] / 1e3:8.1f} kEUR/year")
    print(f"LCOH:   {heat['value'] * MWH:8.1f} EUR/MWh")
    print(f"CO2:    {emitted['value']:8.0f} kg over the day")


if __name__ == "__main__":
    main()
