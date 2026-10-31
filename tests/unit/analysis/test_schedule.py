"""``gm.schedule``: the daily controls of a plant from its demand, and a run of them."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

import gemini as gm
from gemini.analysis import schedule
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
        plant.get_submodule(name).fluid = BRINE
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
    plant.add(
        "HeatingGrid",
        name="users",
        params={"return_temperature": "60 degC", "return_pressure": "6 bar"},
    )
    plant.get_submodule("users").fluid = gm.WATER
    wire(plant)
    plant.boiler.temperature_setpoint = "100 degC"
    return plant


def wire(plant):
    """Connect the brine loop and the heating water, every port named."""
    plant.connect("d0.supply_out", "production.branch1_in")
    plant.connect("d1.supply_out", "production.branch2_in")
    plant.connect("production.fluid_out", "degasser.fluid_in")
    plant.connect("degasser.liquid_out", "hx.hot_in")
    plant.connect("degasser.gas_out", "gas_out")
    plant.connect("power_in", "d0.power_in")
    plant.connect("power_in", "d1.power_in")
    plant.connect("hx.hot_out", "injection.fluid_in")
    plant.connect("injection.branch1_out", "d0.return_in")
    plant.connect("injection.branch2_out", "d1.return_in")
    plant.connect("users.return_out", "hx.cold_in")
    plant.connect("hx.cold_out", "boiler.fluid_in")
    plant.connect("grid.gas_out", "boiler.fuel_in")
    plant.connect("boiler.flue_out", "flue")
    plant.connect("boiler.loss_out", "loss")
    plant.connect("boiler.fluid_out", "users.supply_in")


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
    assert plan["users.flow"].iloc[0] == pytest.approx(FULL / (4217.4 * 40))
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
    delivered = frame["users.supply_in.enthalpy_flow"] - frame["users.return_out.enthalpy_flow"]
    assert delivered.to_numpy() == pytest.approx([1.2 * FULL, 0.4 * FULL], rel=1e-6)
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


def test_outage_days_are_the_lowest_demand_days_and_never_overlap():
    """The first doublet takes the lowest days, the next the lowest left; heat and cold add up."""
    frame = demand(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    frame["cooling_demand"] = [9.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    plan = gm.schedule(plant_of_two(), frame, RULES | {"operating_days": 4})
    assert plan.attrs["outage_days"] == {
        "d0": ["2027-01-02", "2027-01-03"],
        "d1": ["2027-01-04", "2027-01-05"],
    }


def test_an_outage_moves_the_heat_to_the_next_doublet_and_the_boiler():
    """No flow on the outage day; every other day each doublet runs."""
    frame = demand(0.5 * FULL, 1.5 * FULL, 2.5 * FULL, 3.0 * FULL)
    plan = gm.schedule(plant_of_two(), frame, RULES | {"operating_days": 3})
    assert plan["d0.flow"].iloc[0] == 0 and not plan["d0.is_running"].iloc[0]
    assert plan["d1.flow"].iloc[0] == pytest.approx(150 / 3600)
    assert plan["d1.flow"].iloc[1] == 0 and plan["d0.flow"].iloc[1] == pytest.approx(300 / 3600)
    assert plan["boiler_duty"].iloc[1] == pytest.approx(0.5 * FULL)
    assert plan["injection.split_fraction"].iloc[0] == pytest.approx(1.0)


def test_a_doublet_without_a_need_still_runs_its_days():
    """Each doublet runs exactly its days: at the minimum flow when the need is covered."""
    plan = gm.schedule(plant_of_two(), demand(FULL, FULL, FULL), RULES | {"operating_days": 2})
    assert plan.attrs["outage_days"] == {"d0": ["2027-01-01"], "d1": ["2027-01-02"]}
    assert plan["d1.flow"].iloc[2] == pytest.approx(50 / 3600)
    assert plan["d0.is_running"].sum() == plan["d1.is_running"].sum() == 2


def test_a_list_of_dates_takes_every_doublet_off():
    """A plant without doublets running leaves its demand to the boiler, and the run says so."""
    plant = plant_of_two()
    dates = ["2027-01-02", pd.Timestamp("2027-01-02", tz="UTC"), date(2027, 1, 2)]
    rules = RULES | {"operating_days": dates}
    plan = gm.schedule(plant, demand(FULL, FULL), rules)
    assert plan.attrs["outage_days"] == {"d0": ["2027-01-02"], "d1": ["2027-01-02"]}
    assert plan["d0.flow"].iloc[1] == plan["d1.flow"].iloc[1] == 0
    assert plan["boiler_duty"].iloc[1] == pytest.approx(FULL)
    results = gm.simulate(plant, plan)
    assert results.errors() == []
    assert results.to_frame()["users.unmet_demand"].to_numpy() == pytest.approx([0, 0], abs=1e-3)


def test_no_rule_gives_no_outage():
    """The outages are there to read, also without any."""
    plan = gm.schedule(plant_of_two(), demand(FULL), RULES)
    assert plan.attrs["outage_days"] == {"d0": [], "d1": []}


@pytest.mark.parametrize(
    ("days", "message"),
    [
        (0, "more than the 3 days"),
        (1, "more than the 3 days"),
        (4, "expected 0 to 3"),
        (-1, "expected 0 to 3"),
        (["2028-01-01"], "2028-01-01"),
        (["soon"], "soon"),
        ("2027-01-01", "a list of dates"),
        (True, "a list of dates"),
        (1.5, "a list of dates"),
    ],
)
def test_operating_days_that_do_not_fit_are_refused(days, message):
    """Too many outage days, a date outside the demand, or what is no rule."""
    with raises(gm.errors.ValidationError, "invalid_value", match=message):
        gm.schedule(plant_of_two(), demand(FULL, FULL, FULL), RULES | {"operating_days": days})


def split_sources():
    """Return ``d0`` feeding only a heat pump and ``d1`` only an exchanger, on one water loop."""
    plant = plant_of_two()
    spec = plant.to_dict()
    drop = ("production", "degasser", "injection")
    spec["modules"] = {name: item for name, item in spec["modules"].items() if name not in drop}
    spec["modules"]["heat_pump"] = {
        "type": "HeatPump",
        "params": {"mode": "heating", "capacity": "10 MW"},
    }
    spec.pop("outlets", None)
    spec["inlets"] = {"power_in": ["d0.power_in", "d1.power_in", "heat_pump.power_in"]}
    spec["outlets"] = {"flue": "boiler.flue_out", "loss": "boiler.loss_out"}
    spec["connections"] = [
        {"source": "d0.supply_out", "target": "heat_pump.source_in"},
        {"source": "heat_pump.source_out", "target": "d0.return_in"},
        {"source": "d1.supply_out", "target": "hx.hot_in"},
        {"source": "hx.hot_out", "target": "d1.return_in"},
        {"source": "users.return_out", "target": "hx.cold_in"},
        {"source": "hx.cold_out", "target": "heat_pump.sink_in"},
        {"source": "heat_pump.sink_out", "target": "boiler.fluid_in"},
        {"source": "grid.gas_out", "target": "boiler.fuel_in"},
        {"source": "boiler.fluid_out", "target": "users.supply_in"},
    ]
    built = gm.plants.from_dict(spec)
    built.boiler.temperature_setpoint = "100 degC"
    built.heat_pump.temperature_setpoint = "100 degC"
    return built


@pytest.fixture(scope="module")
def split_run():
    """Return the plan and the run of ``split_sources``: ``d0`` off first, then ``d1``."""
    plant = split_sources()
    plan = gm.schedule(plant, demand(0.5 * FULL, FULL, 2 * FULL), RULES | {"operating_days": 2})
    return plan, gm.simulate(plant, plan).to_frame()


def test_a_heat_pump_on_the_brine_of_one_doublet_stops_with_it(split_run):
    """The wiring decides: ``d0`` off stops the heat pump, ``d1`` off does not."""
    plan, frame = split_run
    assert plan["heat_pump.is_running"].tolist() == [False, True, True]
    assert frame["heat_pump.is_running"].iloc[0] == 0 and frame["heat_pump.is_running"].iloc[1] == 1


def test_a_stopped_heat_pump_covers_nothing_before_geothermal():
    """Ordered first, its capacity counts only on the days it runs."""
    rules = RULES | {"order": ["heat_pump", "geothermal", "boiler"], "operating_days": 2}
    plan = gm.schedule(split_sources(), demand(10e6 + 0.5 * FULL, 10e6 + 0.75 * FULL, 25e6), rules)
    assert plan["d1.flow"].iloc[0] == pytest.approx(300 / 3600)
    assert plan["d0.flow"].iloc[1] == pytest.approx(225 / 3600)


def test_a_heat_pump_on_the_mixed_brine_keeps_running():
    """One doublet of two still feeds it; only both off stop it."""
    plant = plant_of_two()
    off = {"d0": np.array([True, True]), "d1": np.array([False, True])}
    assert schedule._doublets_above(plant, "hx", "hot_in", off, set()) == {"d0", "d1"}


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


def test_a_finished_run_ran_the_days_of_the_rule():
    """Two doublets, three days of four each: the plan, the run and the check agree."""
    plant = plant_of_two()
    frame = demand(0.5 * FULL, 1.5 * FULL, 2.5 * FULL, 3.0 * FULL)
    results = gm.simulate(plant, gm.schedule(plant, frame, RULES | {"operating_days": 3}))
    assert results.errors() == []
    checks = gm.checks.operating_days(plant, results, 3)
    assert [item["passed"] for item in checks] == [True, True]
    assert [item["value"]["value"] for item in checks] == [3, 3]


COOLING_SIZES = {
    "heat_pump.capacity": "2 MW",
    "peak_boiler.capacity": "30 MW",
    "absorption_chiller.capacity": "3 MW",
    "adsorption_chiller.capacity": "1 MW",
    "compression_chiller.capacity": "10 MW",
    "absorption_chiller.thermal_cop": 0.5,
    "adsorption_chiller.thermal_cop": 0.25,
    "heating_consumer.return_temperature": "60 degC",
    "cooling_consumer.return_temperature": "28 degC",
}
COOLING_INPUTS = {
    "heat_pump.temperature_setpoint": "100 degC",
    "peak_boiler.temperature_setpoint": "100 degC",
    "compression_chiller.temperature_setpoint": "20 degC",
}


def cooling_plant():
    """Return the plant with every cooling unit: only what a schedule reads is set."""
    plant = gm.plants.get("HeatingCoolingPlant")
    plant.set_params("", COOLING_SIZES)
    plant.heating_consumer.fluid = plant.cooling_consumer.fluid = gm.WATER
    return plant.set_inputs(COOLING_INPUTS)


def cold_demand(cold, heat=1e6):
    """Return one day of heat and cold [W]."""
    frame = demand(heat)
    frame["cooling_demand"] = cold
    return frame


def test_a_heat_pump_and_a_compression_chiller_are_scheduled_together():
    """The plant that "expected at most one": each has its own setpoint."""
    plan = gm.schedule(cooling_plant(), cold_demand(8e6), RULES)
    assert plan["heat_pump.temperature_setpoint"].iloc[0] == pytest.approx(373.15)
    assert plan["compression_chiller.temperature_setpoint"].iloc[0] == pytest.approx(293.15)


def test_heat_driven_units_go_first_and_add_their_drive_heat():
    """Absorption 3 MW, adsorption 1 MW, compression the rest: 3 / 0.5 + 1 / 0.25 of heat."""
    plan = gm.schedule(cooling_plant(), cold_demand(8e6), RULES)
    assert plan["d0.flow"].iloc[0] == pytest.approx(11e6 / (1000 * 4217.4 * 40))
    assert plan["cooling_consumer.flow"].iloc[0] == pytest.approx(8e6 / (4217.4 * 8))


def test_the_units_before_the_last_stop_where_their_share_ends():
    """28 to 20 degC over 8 MW: absorption takes 3 K, adsorption 1 K more, compression the rest."""
    plan = gm.schedule(cooling_plant(), cold_demand(8e6), RULES)
    assert plan["absorption_chiller.temperature_setpoint"].iloc[0] == pytest.approx(298.15)
    assert plan["adsorption_chiller.temperature_setpoint"].iloc[0] == pytest.approx(297.15)
    assert plan["compression_chiller.temperature_setpoint"].iloc[0] == pytest.approx(293.15)


def test_the_cooling_order_rule_changes_who_takes_the_cold():
    """Compression first takes all of it: the heat-driven units stand and draw no heat."""
    rules = RULES | {"cooling_order": ["compression", "absorption", "adsorption"]}
    plan = gm.schedule(cooling_plant(), cold_demand(8e6), rules)
    assert plan["absorption_chiller.temperature_setpoint"].iloc[0] == pytest.approx(301.15)
    assert plan["adsorption_chiller.temperature_setpoint"].iloc[0] == pytest.approx(301.15)


def test_a_unit_left_out_of_the_order_takes_nothing():
    """Absorption alone: the cold beyond its capacity stays with the chain's last unit."""
    rules = RULES | {"cooling_order": ["absorption"]}
    plan = gm.schedule(cooling_plant(), cold_demand(8e6), rules)
    assert plan["adsorption_chiller.temperature_setpoint"].iloc[0] == pytest.approx(298.15)


def test_a_day_without_cold_takes_nothing():
    """No demand, no drive heat and no error."""
    plan = gm.schedule(cooling_plant(), cold_demand(0.0), RULES)
    assert plan["cooling_consumer.flow"].iloc[0] == 0


def test_an_unknown_cooling_kind_is_refused():
    """The rule names what it takes."""
    rules = RULES | {"cooling_order": ["absorptoin"]}
    with raises(gm.errors.ValidationError, "invalid_value", match="cooling_order"):
        gm.schedule(cooling_plant(), cold_demand(1e6), rules)


def test_an_adsorption_chiller_is_dispatched_with_its_own_cop():
    """Alone, its 1 MW of cold draws 4 MW of heat at its COP of 0.25."""
    rules = RULES | {"cooling_order": ["adsorption"]}
    plan = gm.schedule(cooling_plant(), cold_demand(8e6), rules)
    assert plan["d0.flow"].iloc[0] == pytest.approx(5e6 / (1000 * 4217.4 * 40))
