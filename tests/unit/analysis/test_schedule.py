"""``gm.schedule``: the daily controls of a plant from its demand, and a run of them."""

import pandas as pd
import pytest

import gemini as gm
from gemini.backends import settings
from gemini.physics import constants
from tests.fixtures.errors import raises
from tests.fixtures.parity import BACKENDS

BRINE = gm.Fluid(density=1030.0, viscosity=4e-4, specific_heat=4000.0)
DESIGN = {
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
RULES = {
    "order": ["geothermal", "heat_pump", "boiler"],
    "doublet_flow": {"min": "50 m3/h", "max": "300 m3/h"},
    "max_brine_cooling": "40 K",
    "operating_days": None,
}
HEAT_PER_FLOW = 1030.0 * 4000.0 * 40.0
FULL = 300 / 3600 * HEAT_PER_FLOW


def plant_of_two():
    """Return two doublets, a boiler and a heat user, with a named return at 60 degC."""
    plant = gm.Plant("Two")
    for name in ("d0", "d1"):
        plant.add("Doublet", name=name, params=DESIGN)
        plant.get_module(name).fluid = BRINE
    plant.add("Mixer", name="production")
    plant.add("Degasser", name="degasser")
    plant.add(
        "HeatExchanger",
        name="hx",
        params=dict(
            thermal_conductance=2e6,
            hot_nominal_pressure_drop=0,
            cold_nominal_pressure_drop=0,
            hot_nominal_mass_flow=170.0,
            cold_nominal_mass_flow=170.0,
        ),
    )
    plant.add("Splitter", name="injection")
    plant.add("GasGrid", name="grid")
    plant.add("Boiler", name="boiler", params={"capacity": "40 MW", "efficiency": 0.9})
    plant.add("HeatConsumer", name="users", params={"minimum_return_temperature": "40 degC"})
    wire(plant)
    plant.boiler.temperature_setpoint = "100 degC"
    water = gm.WATER.model_dump(mode="json")
    plant.boundary = {"root_inputs": {"heating_return": {"T": 333.15, "p": 6e5, "fluid": water}}}
    return plant


def wire(plant):
    """Connect the brine loop and the heating water, every port named."""
    plant.connect("d0.supply_out", "production.first_in")
    plant.connect("d1.supply_out", "production.second_in")
    plant.connect("production.mixed_out", "degasser.inlet")
    plant.connect("degasser.liquid", "hx.hot_in")
    plant.connect("degasser.gas", "gas_out")
    plant.connect("hx.hot_out", "injection.feed_in")
    plant.connect("injection.first_out", "d0.return_in")
    plant.connect("injection.second_out", "d1.return_in")
    plant.connect("heating_return", "hx.cold_in")
    plant.connect("hx.cold_out", "boiler.inlet")
    plant.connect("grid.outlet", "boiler.fuel_in")
    plant.connect("boiler.gas_out", "boiler_gas")
    plant.connect("boiler.outlet", "users.supply_in")
    plant.connect("users.return_out", "heating_out")


def demand(*heat):
    """Return a daily demand of the given heat [W] from 2027-01-01."""
    index = pd.date_range("2027-01-01", periods=len(heat), freq="D", tz="UTC", name="time")
    return pd.DataFrame({"heating_demand": heat}, index=index)


def test_doublets_run_in_order_at_the_flow_of_the_need():
    """A small need runs the first; a large one fills it and starts the second."""
    plan = gm.schedule(plant_of_two(), demand(0.5 * FULL, 1.5 * FULL), RULES)
    assert plan["d0.flow"].iloc[0] == pytest.approx(150 / 3600)
    assert plan["d1.flow"].iloc[0] == 0 and not plan["d1.is_running"].iloc[0]
    assert plan["d0.flow"].iloc[1] == pytest.approx(300 / 3600)
    assert plan["d1.flow"].iloc[1] == pytest.approx(150 / 3600)


def test_below_the_minimum_a_doublet_runs_at_the_minimum():
    """Less cooling, never less flow, while it runs."""
    plan = gm.schedule(plant_of_two(), demand(0.01 * FULL), RULES)
    assert plan["d0.flow"].iloc[0] == pytest.approx(50 / 3600)


def test_the_boiler_covers_what_the_doublets_cannot():
    """The plan says how much that is, on design values."""
    plan = gm.schedule(plant_of_two(), demand(2.5 * FULL), RULES)
    assert plan["boiler_duty"].iloc[0] == pytest.approx(0.5 * FULL)


def test_a_source_ordered_first_lowers_the_need_of_the_doublets():
    """With the boiler first the doublets get what its capacity leaves."""
    rules = RULES | {"order": ["boiler", "geothermal", "heat_pump"]}
    plan = gm.schedule(plant_of_two(), demand(40e6 + FULL / 2), rules)
    assert plan["d0.flow"].iloc[0] == pytest.approx(150 / 3600)


def test_the_plan_names_its_columns_after_what_they_drive():
    """Dotted control paths, ``port.field``, and the demand itself."""
    plan = gm.schedule(plant_of_two(), demand(FULL), RULES)
    assert plan["heating_demand"].iloc[0] == FULL
    assert plan["users.heat_demand"].iloc[0] == FULL
    assert plan["d0.esp.frequency"].iloc[0] == float(constants.ESP_REFERENCE_FREQUENCY)
    assert plan["d0.reservoir.production_rate"].iloc[0] == pytest.approx(300 / 3600 * 1030)
    assert plan["boiler.temperature_setpoint"].iloc[0] == pytest.approx(373.15)
    assert plan["heating_return.m_dot"].iloc[0] == pytest.approx(FULL / (4217.4 * 40))
    assert str(plan.index.tz) == "UTC"


def test_the_injected_brine_is_shared_as_the_doublets_produce():
    """``split_fraction`` is the share of the second outlet, the second doublet here."""
    plan = gm.schedule(plant_of_two(), demand(1.5 * FULL), RULES)
    assert plan["injection.split_fraction"].iloc[0] == pytest.approx(1 / 3)


def test_the_plan_runs_without_a_binding_and_leaves_the_plant_alone():
    """``schedule`` then ``simulate``; the plant holds no new binding."""
    plant = plant_of_two()
    before = plant.to_dict()
    plan = gm.schedule(plant, demand(1.2 * FULL, 0.4 * FULL), RULES)
    assert plant.to_dict() == before and plant.bindings == {}
    results = gm.simulate(plant, plan)
    frame = results.to_frame()
    assert frame["users.heat_supplied"].to_numpy() == pytest.approx(
        [1.2 * FULL, 0.4 * FULL], rel=1e-6
    )
    assert frame["users.unmet_demand"].to_numpy() == pytest.approx([0, 0], abs=1e-3)


def test_a_plan_is_the_same_on_every_backend():
    """The plan runs on arrays, whatever backend is set around it."""
    plant = plant_of_two()
    expected = gm.schedule(plant, demand(1.2 * FULL, 0.4 * FULL), RULES)
    for backend in BACKENDS:
        with settings(backend=backend):
            plan = gm.schedule(plant, demand(1.2 * FULL, 0.4 * FULL), RULES)
        pd.testing.assert_frame_equal(plan, expected)


def test_unmet_demand_is_no_error():
    """A boiler too small leaves demand unmet, which the run reports."""
    plant = plant_of_two()
    plant.set_params("boiler", {"capacity": "1 MW"})
    results = gm.simulate(plant, gm.schedule(plant, demand(5 * FULL), RULES))
    assert results.errors() == [] and results.to_frame()["users.unmet_demand"].iloc[0] > 0


@pytest.mark.parametrize("days", [330, ["2027-07-01"]], ids=["count", "outages"])
def test_operating_days_wait_for_a_decision(days):
    """The name is final; what 330 daily steps mean is not decided."""
    with pytest.raises(gm.errors.NotImplementedYet, match="330"):
        gm.schedule(plant_of_two(), demand(FULL), RULES | {"operating_days": days})


def test_a_rule_that_does_not_fit_is_refused():
    """An unknown rule, or a source that does not exist."""
    with raises(gm.errors.ValidationError, "unknown_name"):
        gm.schedule(plant_of_two(), demand(FULL), RULES | {"spare": 1})
    with raises(gm.errors.ValidationError, "invalid_value"):
        gm.schedule(plant_of_two(), demand(FULL), RULES | {"order": ["sun"]})


def test_a_missing_setpoint_is_named():
    """The supply temperature is a design value."""
    plant = plant_of_two()
    plant.boiler._input_values.clear()
    with raises(gm.errors.ValidationError, "invalid_design") as caught:
        gm.schedule(plant, demand(FULL), RULES)
    assert caught.value.path == "boiler.temperature_setpoint"


def test_the_demand_needs_its_heating_column():
    """Without it there is nothing to schedule."""
    with raises(gm.errors.ValidationError, "missing_column"):
        gm.schedule(plant_of_two(), demand(FULL).rename(columns={"heating_demand": "x"}), RULES)
