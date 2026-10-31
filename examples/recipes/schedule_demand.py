"""Plan a year of one doublet and a boiler from the heating demand, then simulate the plan.

Shows ``gm.profiles.get``, ``gm.schedule`` and ``gm.simulate`` on a small plant built from a
doublet's depth. The doublet design, the sizes and the return temperature are assumptions of this
recipe and it prints them as such.

Run with ``python examples/recipes/schedule_demand.py``.
"""

import gemini as gm

BRINE = gm.Fluid(density="1030 kg/m3", viscosity="0.4 mPa*s", specific_heat="4000 J/kg/K")
DOUBLET = {
    "depth": "2500 m",
    "gradient": "30 K/km",
    "surface_temperature": "12 degC",
    "permeability": "200 mD",
    "thickness": "100 m",
    "well_diameter": "0.244 m",
    "nominal_flow": "300 m3/h",
    "pump_efficiency": 0.7,
    "nominal_wellhead_pressure": "10 bar",
}
EXCHANGER = {
    "thermal_conductance": "2000000 W/K",
    "hot_nominal_pressure_drop": "0 bar",
    "cold_nominal_pressure_drop": "0 bar",
    "hot_nominal_mass_flow": "85 kg/s",
    "cold_nominal_mass_flow": "85 kg/s",
}
RULES = {
    "order": ["geothermal", "boiler"],
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": None,
}


def build():
    """Return a doublet, a heat exchanger and a boiler that serve a heating grid."""
    plant = gm.Plant("ScheduledHeat")
    plant.add("Doublet", name="d0", params=DOUBLET)
    plant.d0.fluid = BRINE
    plant.add("HeatExchanger", name="hx", params=EXCHANGER)
    plant.add("Boiler", name="boiler", params={"capacity": "40 MW", "efficiency": 0.9})
    users = {"return_temperature": "60 degC", "return_pressure": "6 bar"}
    plant.add("HeatingGrid", name="users", params=users)
    plant.users.fluid = gm.WATER
    plant.add("GasGrid", name="gas")
    plant.add("ElectricityGrid", name="grid")
    plant.add("Atmosphere", name="air")
    plant.connect("d0.supply_out", "hx.hot_in")
    plant.connect("hx.hot_out", "d0.return_in")
    plant.connect("users.return_out", "hx.cold_in")
    plant.connect("hx.cold_out", "boiler.fluid_in")
    plant.connect("boiler.fluid_out", "users.supply_in")
    plant.connect("gas.gas_out", "boiler.fuel_in")
    plant.connect("grid.power_out", "d0.power_in")
    plant.connect("boiler.flue_out", "air.gas_in")
    plant.connect("boiler.loss_out", "air.heat_in")
    plant.boiler.temperature_setpoint = "100 degC"
    plant.air.temperature = "10 degC"
    return plant


def main():
    """Schedule the demand of 2027, simulate the plan and print what it covers."""
    plant = build()
    print("Assumptions: a 2500 m doublet, 40 MW boiler, return at 60 degC, supply at 100 degC")
    plan = gm.schedule(plant, gm.profiles.get("heating_demand"), RULES)
    lowest = gm.units.convert(plan["d0.flow"].min(), "m3/s", "m3/h")
    highest = gm.units.convert(plan["d0.flow"].max(), "m3/s", "m3/h")
    print(f"Days planned:     {len(plan)}")
    print(f"Doublet flow:     {lowest:.0f} to {highest:.0f} m³/h")
    print(f"Boiler, peak:     {plan['boiler_duty'].max() / 1e6:.2f} MW")
    results = gm.simulate(plant, plan)
    totals = gm.kpi.totals(plant, results)
    print(f"Heat delivered:   {totals['heat_delivered']['value'] / 3.6e12:.2f} GWh")
    print(f"Gas bought:       {totals['gas_bought']['value'] / 3.6e12:.2f} GWh")
    print(f"Electricity:      {totals['electricity_bought']['value'] / 3.6e12:.2f} GWh")


if __name__ == "__main__":
    main()
