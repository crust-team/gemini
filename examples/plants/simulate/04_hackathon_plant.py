"""The hackathon case: two doublets, heat exchanger, heat pump, gas boiler and absorption chiller.

Builds the plant of the challenge requirements with the design APIs, schedules 2027 from the daily
demand, simulates it and prints the limits, the KPIs, the emissions and the economics. The
reservoir, brine, limits and supply temperatures are the challenge's. The return temperatures, the
sizes of the exchanger, heat pump, boiler and chiller and every price are assumptions of this
example, not results, and it prints them as such.

Run with::

    PYTHONPATH=. python examples/plants/simulate/04_hackathon_plant.py
"""

import pandas as pd

import gemini as gm

HEATING_RETURN = 333.15
"""Assumed temperature [K] of the heating return, 60 degC."""

COOLING_RETURN = 298.15
"""Assumed temperature [K] of the cooling return, 25 degC."""

HEATING_GRID = {"return_temperature": HEATING_RETURN, "return_pressure": 6e5}
COOLING_GRID = {
    "return_temperature": COOLING_RETURN,
    "return_pressure": 4e5,
    "dew_point_margin": 1.0,
}

AMBIENT = 283.15
"""Assumed temperature [K] of the air, 10 degC."""

COOLING_WATER = 288.15
"""Assumed temperature [K] of the water that cools the chiller, 15 degC."""

COOLING_WATER_FLOW = 800.0
"""Assumed flow [kg/s] of the water that cools the chiller."""

CHILLER_COOLER = {
    "cooler_type": "dry",
    "capacity": "40 MW",
    "approach": 5.0,
    "specific_fan_power": 0.02,
    "loop_pressure": 3e5,
}

HEATING_SUPPLY = "100 degC"
COOLING_SUPPLY = "20 degC"

BRINE = gm.Fluid(
    density="1030 kg/m3",
    viscosity="0.4 mPa*s",
    gas_liquid_ratio="0.8 Nm3/m3",
    gas_composition={"CH4": 0.8, "CO2": 0.2},
)
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
    "thermal_conductance": 1.5e6,
    "hot_nominal_pressure_drop": 0,
    "cold_nominal_pressure_drop": 0,
    "hot_nominal_mass_flow": 171.7,
    "cold_nominal_mass_flow": 178.0,
}
HEAT_PUMP = {
    "mode": "heating",
    "capacity": "15 MW",
    "minimum_source_outlet_temperature": "47 degC",
}
CHILLER = {
    "mode": "chiller",
    "capacity": "10 MW",
    "characteristic_slope": 7e5,
    "minimum_driving_difference": 10.0,
    "rejection_coefficient": 2.2,
    "evaporator_coefficient": 1.2,
    "auxiliary_power_ratio": 0.01,
}
RULES = {
    "order": ["geothermal", "heat_pump", "boiler"],
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": None,
}
ASSUMPTIONS = dict(
    discount_rate=0.05,
    lifetime_years=25,
    electricity_price=100.0 / 3.6e9,
    gas_price=40.0,
    heat_price=60.0 / 3.6e9,
    cold_price=60.0 / 3.6e9,
    electricity_emission_factor=0.3 / 3.6e6,
    pump_cost=0.5,
    chiller_cost=0.3,
    exchanger_cost=0.5,
    flare_cost=1e5,
    makeup_cost=5e4,
)
"""Placeholders, not data: the prices and the factors without a source are this example's."""


def add_modules(plant):
    """Add every module of the plant."""
    for name in ("d0", "d1"):
        plant.add("Doublet", name=name, params=DOUBLET)
        plant.get_module(name).fluid = BRINE
    plant.add("Mixer", name="production")
    plant.add("Degasser", name="degasser", params={"separation_efficiency": 1.0})
    plant.add("HeatExchanger", name="hx", params=EXCHANGER)
    plant.add("Splitter", name="injection")
    plant.add("GasGrid", name="gas_grid")
    plant.add("GasMakeup", name="makeup")
    plant.add("Boiler", name="boiler", params={"capacity": "30 MW", "efficiency": 0.9})
    plant.add("Flare", name="flare")
    plant.add("ElectricityGrid", name="grid")
    plant.add("Atmosphere", name="air")
    plant.add("Cooler", name="chiller_cooler", params=CHILLER_COOLER)
    plant.add("HeatPump", name="heat_pump", params=HEAT_PUMP)
    plant.add("Splitter", name="loads")
    plant.add("Mixer", name="heat_return")
    plant.add("HeatingGrid", name="heat_users", params=HEATING_GRID)
    plant.add("AbsorptionUnit", name="chiller", params=CHILLER)
    plant.add("CoolingGrid", name="cool_users", params=COOLING_GRID)
    plant.get_module("heat_users").fluid = gm.WATER
    plant.get_module("cool_users").fluid = gm.WATER
    plant.get_module("chiller_cooler").fluid = gm.WATER


def connect_brine(plant):
    """Wire the brine from the doublets through the exchanger and heat pump and back."""
    plant.connect("d0.supply_out", "production.branch1_in")
    plant.connect("d1.supply_out", "production.branch2_in")
    plant.connect("production.fluid_out", "degasser.fluid_in")
    plant.connect("degasser.liquid_out", "hx.hot_in")
    plant.connect("hx.hot_out", "heat_pump.source_in")
    plant.connect("heat_pump.source_out", "injection.fluid_in")
    plant.connect("injection.branch1_out", "d0.return_in")
    plant.connect("injection.branch2_out", "d1.return_in")


def connect_power(plant):
    """Wire every consumer of electricity to the grid."""
    for name in ("d0", "d1", "heat_pump", "chiller", "chiller_cooler"):
        plant.connect("grid.power_out", f"{name}.power_in")


def connect_gas(plant):
    """Wire the co-produced gas: the boiler takes what it needs and the flare burns the rest."""
    plant.connect("degasser.gas_out", "makeup.gas_in")
    plant.connect("gas_grid.gas_out", "makeup.grid_in")
    plant.connect("makeup.fuel_out", "boiler.fuel_in")
    plant.connect("makeup.excess_out", "flare.gas_in")


def connect_water(plant):
    """Wire the heating, chilled and cooling water."""
    plant.connect("heat_users.return_out", "hx.cold_in")
    plant.connect("hx.cold_out", "heat_pump.sink_in")
    plant.connect("heat_pump.sink_out", "boiler.fluid_in")
    plant.connect("boiler.fluid_out", "loads.fluid_in")
    plant.connect("loads.branch1_out", "heat_return.branch1_in")
    plant.connect("loads.branch2_out", "chiller.generator_in")
    plant.connect("chiller.generator_out", "heat_return.branch2_in")
    plant.connect("heat_return.fluid_out", "heat_users.supply_in")
    plant.connect("cool_users.return_out", "chiller.chilled_in")
    plant.connect("chiller.chilled_out", "cool_users.supply_in")
    plant.connect("chiller.cooling_out", "chiller_cooler.fluid_in")
    plant.connect("chiller_cooler.fluid_out", "chiller.cooling_in")


def connect_air(plant):
    """Wire what the plant releases and the chiller's cooler to the air."""
    plant.connect("boiler.flue_out", "air.gas_in")
    plant.connect("flare.flue_out", "air.gas_in")
    plant.connect("air.air_out", "chiller_cooler.air_in")
    plant.connect("chiller_cooler.air_out", "air.air_in")


def set_boundaries(plant):
    """Set the setpoints of the design and the assumed cooling water and air."""
    plant.heat_pump.temperature_setpoint = HEATING_SUPPLY
    plant.boiler.temperature_setpoint = HEATING_SUPPLY
    plant.chiller.temperature_setpoint = COOLING_SUPPLY
    plant.cool_users.indoor_temperature = "26 degC"
    plant.cool_users.indoor_relative_humidity = 0.5
    plant.chiller_cooler.temperature_setpoint = COOLING_WATER
    plant.chiller_cooler.flow = COOLING_WATER_FLOW
    plant.air.temperature = AMBIENT


def build():
    """Return the hackathon plant."""
    plant = gm.Plant("Hackathon")
    add_modules(plant)
    connect_brine(plant)
    connect_power(plant)
    connect_gas(plant)
    connect_water(plant)
    connect_air(plant)
    set_boundaries(plant)
    plant.validate()
    return plant


def hackathon_limits():
    """Return the hard limits of the challenge."""
    limits = gm.checks.Limits()
    limits.add("d*.flow", min="50 m3/h", max="300 m3/h")
    limits.add("d*.brine_cooling", max="40 K")
    limits.add("boiler.fluid_out_T", min="100 degC")
    return limits


def print_assumptions():
    """Say what this example assumes rather than takes from the challenge."""
    print("Assumptions of this example, not of the challenge:")
    print("  heating return 60 degC, cooling return 25 degC, chiller cooling water 15 degC")
    print("  air 10 degC; the chiller's dry cooler: 5 K approach, 2 % fan power")
    print("  heat exchanger, heat pump, boiler and chiller sizes; 1000 m drainage radius")
    print("  discount rate, lifetime, every price and the cost factors without a source")


def print_run(results):
    """Print the delivered energy and what remained unmet."""
    frame = results.to_frame()
    hours = 24.0
    gwh = hours / 1e9
    print("\nThe year, in daily steps:")
    print(f"  heat delivered    {frame['heat_users.heat_supplied'].sum() * gwh:8.2f} GWh")
    print(f"  heat unmet        {frame['heat_users.unmet_demand'].sum() * gwh:8.2f} GWh")
    print(f"  cold delivered    {frame['cool_users.heat_absorbed'].sum() * gwh:8.2f} GWh")
    print(f"  cold unmet        {frame['cool_users.unmet_sensible'].sum() * gwh:8.2f} GWh")
    print(f"  boiler, peak      {frame['boiler.duty'].max() / 1e6:8.2f} MW")
    print(f"  heat pump, peak   {frame['heat_pump.useful_duty'].max() / 1e6:8.2f} MW")
    print(f"  gas co-produced   {frame['boiler.fuel_coproduced'].sum() * gwh:8.2f} GWh burnt")
    print(f"  gas purchased     {frame['boiler.fuel_purchased'].sum() * gwh:8.2f} GWh")
    print(f"  supply, lowest    {frame['boiler.fluid_out_T'].min() - 273.15:8.2f} degC")


def print_limits(checks):
    """Print each limit of the challenge, in the units of the challenge."""
    print("\nLimits:")
    for item in checks:
        result = "ok" if item["passed"] else "VIOLATED"
        print(
            f"  {item['name']:<26} {result:<9} worst {item['value']['value']:.4g} "
            f"{item['value']['unit']}"
        )


def print_kpis(kpis):
    """Print the KPIs of the run."""
    print("\nKPIs:")
    for name, item in kpis.items():
        print(f"  {name:<18} {item['value']:.4g} {item['unit']}")


def print_economics(plant, results, values):
    """Print the economics in the units people read; every price is a placeholder."""
    investment = gm.economics.capex(plant, values)
    yearly = gm.economics.opex(plant, results, values)
    emitted = gm.economics.co2(plant, results, values)
    print("\nEconomics, on the placeholder prices above:")
    print(f"  capex    {investment['value'] / 1e6:8.1f} MEUR ({investment['price_year']['value']})")
    print(f"  opex     {yearly['value'] / 1e6:8.2f} MEUR/year")
    print(f"  CO2-eq   {emitted['value'] / 1e6:8.1f} kt/year")
    for name, function in (("LCOH", gm.economics.lcoh), ("LCOC", gm.economics.lcoc)):
        print(
            f"  {name}     {function(plant, results, assumptions=values)['value'] * 3.6e9:8.1f} "
            "EUR/MWh"
        )
    print(
        f"  NPV      {gm.economics.npv(plant, results, assumptions=values)['value'] / 1e6:8.1f} "
        "MEUR"
    )
    print(f"  payback  {gm.economics.payback(plant, results, values)['value']:8.1f} years")


plant = build()
demand = pd.concat([gm.profiles.get("heating_demand"), gm.profiles.get("cooling_demand")], axis=1)
print_assumptions()
try:
    plan = gm.schedule(plant, demand, RULES)
except gm.errors.NotImplementedYet as error:
    print(f"\nStopped at gm.schedule: {error}")
    raise SystemExit(0) from error
results = gm.simulate(plant, plan)
print_run(results)
print_limits(gm.checks.limits(plant, results, hackathon_limits()))
print_kpis(gm.kpi.compute(plant, results))
frame = results.to_frame()
heat = frame["heat_users.heat_supplied"].sum()
share = heat / (heat + frame["cool_users.heat_absorbed"].sum())
print_economics(plant, results, gm.economics.Assumptions(heat_cost_share=share, **ASSUMPTIONS))
