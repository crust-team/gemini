"""The co-produced gas chain: degasser, makeup, boiler and flare, closed in mass and energy."""

import pytest

import gemini as gm
from gemini.modules import energy_balance, mass_balance
from gemini.physics import combustion, gas

BRINE = gm.Fluid(
    density="1030 kg/m3",
    viscosity="0.4 mPa*s",
    gas_liquid_ratio="0.8 Nm3/m3",
    gas_composition={"CH4": 0.8, "CO2": 0.2},
)
PRODUCED = gm.Stream(flow="300 m3/h", T="80 degC", p="10 bar", fluid=BRINE)
WATER = gm.Stream(flow="20 kg/s", T="60 degC", p="5 bar", fluid=gm.WATER)


def chain():
    """Return the plant of ``api.md``: gas to the makeup, the boiler and the flare."""
    plant = gm.Plant("Chain")
    plant.add("Degasser", name="degasser", params={"separation_efficiency": 1.0})
    plant.add("GasGrid", name="grid")
    plant.add("GasMakeup", name="makeup")
    plant.add("Boiler", name="boiler", params={"capacity": "30 MW", "efficiency": 0.9})
    plant.add("Flare", name="flare")
    plant.add("Atmosphere", name="air")
    plant.connect("boiler.flue_out", "air.gas_in")
    plant.connect("flare.flue_out", "air.gas_in")
    plant.connect("produced", "degasser.fluid_in")
    plant.connect("degasser.liquid_out", "fluid_out")
    plant.connect("degasser.gas_out", "makeup.gas_in")
    plant.connect("grid.gas_out", "makeup.grid_in")
    plant.connect("makeup.fuel_out", "boiler.fuel_in")
    plant.connect("makeup.excess_out", "flare.gas_in")
    plant.connect("water_in", "boiler.fluid_in")
    plant.connect("boiler.fluid_out", "water_out")
    assert {item["code"] for item in plant.validate(on_error="record")} == {"root_plant_port"}
    return plant


def run(setpoint):
    """Return the plant and one call at a boiler setpoint."""
    plant = chain()
    plant.boiler.temperature_setpoint = setpoint
    plant.air.temperature = "15 degC"
    return plant, plant(produced=PRODUCED, water_in=WATER)


def test_a_boiler_with_enough_gas_buys_nothing_and_the_surplus_reaches_the_flare():
    """The gas of 300 m3/h of brine covers a small duty; the rest is burned at the flare."""
    _, result = run("65 degC")
    boiler, flare = result.leaves()["boiler"].outputs, result.leaves()["flare"].outputs
    assert boiler.fuel_purchased == 0 and boiler.fuel_coproduced == pytest.approx(boiler.fuel)
    gas_flow = result.leaves()["degasser"].outputs.gas_mass_flow
    assert flare.burned_mass_flow == pytest.approx(gas_flow - boiler.burned_mass_flow)
    assert flare.burned_mass_flow > 0


def test_a_boiler_short_of_gas_buys_the_rest_and_nothing_reaches_the_flare():
    """A large duty burns all the gas and buys what is left."""
    _, result = run("95 degC")
    boiler, flare = result.leaves()["boiler"].outputs, result.leaves()["flare"].outputs
    assert boiler.fuel_purchased > 0 and flare.burned_mass_flow == pytest.approx(0, abs=1e-12)
    assert boiler.fuel_coproduced + boiler.fuel_purchased == pytest.approx(boiler.fuel)


def test_without_co_produced_gas_the_grid_covers_everything():
    """``grid.gas_out`` to ``boiler.fuel_in``, the other wiring of the chain."""
    plant = gm.Plant("Grid")
    plant.add("GasGrid", name="grid")
    plant.add("Boiler", name="boiler", params={"capacity": "30 MW", "efficiency": 0.9})
    plant.add("Atmosphere", name="air")
    plant.connect("boiler.flue_out", "air.gas_in")
    plant.connect("grid.gas_out", "boiler.fuel_in")
    plant.connect("water_in", "boiler.fluid_in")
    plant.connect("boiler.fluid_out", "water_out")
    plant.boiler.temperature_setpoint = "70 degC"
    plant.air.temperature = "15 degC"
    leaves = plant(water_in=WATER).leaves()
    outputs = leaves["boiler"].outputs
    assert outputs.fuel_coproduced == 0 and outputs.fuel_purchased == pytest.approx(outputs.fuel)
    assert leaves["air"].outputs.co2_emission == pytest.approx(
        outputs.fuel * gas.emission_per_energy(gas.GRID_COMPOSITION)
    )


@pytest.mark.parametrize("setpoint", ["65 degC", "95 degC"], ids=["surplus", "short"])
def test_the_chain_closes_its_mass_and_energy_balance(setpoint):
    """Every kilogram that enters leaves or burns, and every watt is accounted for."""
    plant, result = run(setpoint)
    assert mass_balance(plant, result)["relative_residual"] < 1e-12
    assert energy_balance(plant, result)["relative_thermal_residual"] < 1e-12


def test_the_chain_conserves_the_carbon_it_reports():
    """The CO2 of boiler and flare is what the gas gives, with the flare's efficiency."""
    _, result = run("65 degC")
    gas_flow = result.leaves()["degasser"].outputs.gas_mass_flow
    composition = BRINE.gas_composition
    boiler_burnt = result.leaves()["boiler"].outputs.burned_mass_flow
    flared = gas_flow - boiler_burnt
    formed = gas.combustion_co2(composition)
    carried = gas.mass_fraction(composition, "CO2")
    expected = boiler_burnt * (formed + carried)
    expected += flared * (carried + combustion.FLARE_EFFICIENCY * formed)
    assert result.leaves()["air"].outputs.co2_emission == pytest.approx(expected)
