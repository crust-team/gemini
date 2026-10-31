"""Check the balances of a run and read the totals at the plant's edge.

Shows ``gm.modules.energy_balance`` and ``gm.modules.mass_balance`` on one call,
``gm.checks.plant_balance`` on a run and ``gm.kpi.totals``, on a boiler that serves a heating grid.
Its sizes and the demand are assumptions of this recipe.

Run with ``python examples/recipes/energy_balance.py``.
"""

import gemini as gm

DAY = gm.Clock.days(2027, 1, 1, days=1)
INPUTS = {
    "users.heat_demand": (500, "kW"),
    "users.flow": (15, "kg/s"),
    "boiler.temperature_setpoint": (90, "degC"),
}


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


def module_balance():
    """Call one boiler and audit that call."""
    boiler = gm.modules.Boiler().update_params(capacity="1 MW", efficiency=0.9)
    result = boiler(
        fluid_in=gm.Stream(flow="10 kg/s", T="60 degC", p="3 bar"),
        fuel_in=gm.modules.GasGrid().offer()["gas_out"],
        temperature_setpoint="80 degC",
    )
    audit = gm.modules.energy_balance(boiler, result)
    print(f"Boiler energy in:    {audit['in'] / 1e6:.3f} MW")
    print(f"Boiler energy out:   {audit['out'] / 1e6:.3f} MW")
    print(f"Boiler residual:     {audit['relative_residual']:.1e} of the energy in")
    print(f"Boiler mass:         {gm.modules.mass_balance(boiler, result)['residual']} kg/s")


def main():
    """Audit one call, simulate a day, check the plant and read its edge."""
    print("Assumptions: 500 kW demand on 15 kg/s of water, a 1 MW boiler at 90 % efficiency")
    module_balance()
    profiles = {
        path: gm.Profile.constant(value, unit=unit, clock=DAY)
        for path, (value, unit) in INPUTS.items()
    }
    plant = build()
    results = gm.simulate(plant, gm.Dataset.from_profiles(profiles), clock=DAY)
    checks = gm.checks.plant_balance(plant, results)
    closed = sum(check["passed"] is True for check in checks)
    print(f"Balances that close: {closed} of {len(checks)}")
    totals = gm.kpi.totals(plant, results)
    print(f"Heat delivered:      {totals['heat_delivered']['value'] / 3.6e9:.2f} MWh")
    print(f"CO2 emitted:         {totals['co2_emitted']['value']:.0f} kg")
    print(f"Losses:              {totals['losses']['value'] / 3.6e9:.2f} MWh")


if __name__ == "__main__":
    main()
