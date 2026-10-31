"""``gm.schedule``: the controls of a plant from its demand at any step, and a run of them."""

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
from tests.fixtures.sample_problems import HACKATHON_2027, treatment_plant

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
    "operating_time": None,
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


def demand(*heat, freq="D"):
    """Return a demand of the given heat [W] from 2027-01-01, daily unless ``freq`` says."""
    index = pd.date_range("2027-01-01", periods=len(heat), freq=freq, tz="UTC", name="time")
    return pd.DataFrame({"heating_demand": heat}, index=index)


def at(day, hour=0):
    """Return the ISO text of an hour of a day of 2027-01."""
    return f"2027-01-{day:02d}T{hour:02d}:00:00+00:00"


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


def test_outage_steps_are_the_lowest_demand_days_and_never_overlap():
    """The first doublet takes the lowest days, the next the lowest left; heat and cold add up."""
    frame = demand(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    frame["cooling_demand"] = [9.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    plan = gm.schedule(plant_of_two(), frame, RULES | {"operating_time": "4 d"})
    assert plan.attrs["outages"] == {
        "d0": [at(2), at(3)],
        "d1": [at(4), at(5)],
    }


def test_an_outage_moves_the_heat_to_the_next_doublet_and_the_boiler():
    """No flow on the outage day; every other day each doublet runs."""
    frame = demand(0.5 * FULL, 1.5 * FULL, 2.5 * FULL, 3.0 * FULL)
    plan = gm.schedule(plant_of_two(), frame, RULES | {"operating_time": "3 d"})
    assert plan["d0.flow"].iloc[0] == 0 and not plan["d0.is_running"].iloc[0]
    assert plan["d1.flow"].iloc[0] == pytest.approx(150 / 3600)
    assert plan["d1.flow"].iloc[1] == 0 and plan["d0.flow"].iloc[1] == pytest.approx(300 / 3600)
    assert plan["boiler_duty"].iloc[1] == pytest.approx(0.5 * FULL)
    assert plan["injection.split_fraction"].iloc[0] == pytest.approx(1.0)


def test_a_doublet_without_a_need_still_runs_its_days():
    """Each doublet runs exactly its days: at the minimum flow when the need is covered."""
    plan = gm.schedule(plant_of_two(), demand(FULL, FULL, FULL), RULES | {"operating_time": "2 d"})
    assert plan.attrs["outages"] == {"d0": [at(1)], "d1": [at(2)]}
    assert plan["d1.flow"].iloc[2] == pytest.approx(50 / 3600)
    assert plan["d0.is_running"].sum() == plan["d1.is_running"].sum() == 2


def test_a_list_of_dates_takes_every_doublet_off():
    """A plant without doublets running leaves its demand to the boiler, and the run says so."""
    plant = plant_of_two()
    dates = ["2027-01-02", pd.Timestamp("2027-01-02", tz="UTC"), date(2027, 1, 2)]
    rules = RULES | {"operating_time": dates}
    plan = gm.schedule(plant, demand(FULL, FULL), rules)
    assert plan.attrs["outages"] == {"d0": [at(2)], "d1": [at(2)]}
    assert plan["d0.flow"].iloc[1] == plan["d1.flow"].iloc[1] == 0
    assert plan["boiler_duty"].iloc[1] == pytest.approx(FULL)
    results = gm.simulate(plant, plan)
    assert results.errors() == []
    assert results.to_frame()["users.unmet_demand"].to_numpy() == pytest.approx([0, 0], abs=1e-3)


def test_no_rule_gives_no_outage():
    """The outages are there to read, also without any."""
    plan = gm.schedule(plant_of_two(), demand(FULL), RULES)
    assert plan.attrs["outages"] == {"d0": [], "d1": []}


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ("0 d", "a duration"),
        ("1 d", "more than the 3 steps"),
        ("4 d", "expected 0 to 3"),
        (0.2, "more than the 3 steps"),
        (["2028-01-01"], "2028-01-01"),
        ([{"start": "2028-01-01", "end": "2028-01-02"}], "2028-01-01"),
        (["soon"], "a list of outages"),
        ("2027-01-01", "a list of outages"),
        ("soon", "a duration"),
        (True, "a fraction"),
        (1.5, "a fraction"),
        (-0.1, "a fraction"),
        (330, "a fraction"),
        ([{"start": "2027-01-02"}], "a list of outages"),
        ([{"start": "2027-01-03", "end": "2027-01-02"}], "a list of outages"),
        ([{"start": "2027-01-02", "end": "2027-01-03", "by": 1}], "a list of outages"),
    ],
)
def test_operating_time_that_does_not_fit_is_refused(rule, message):
    """Too many outage steps, an outage outside the demand, or what is no rule."""
    with raises(gm.errors.ValidationError, "invalid_value", match=message):
        gm.schedule(plant_of_two(), demand(FULL, FULL, FULL), RULES | {"operating_time": rule})


@pytest.mark.parametrize("rule", ["2 d", 0.5])
def test_a_duration_or_fraction_needs_a_constant_step(rule):
    """One row, or uneven rows, have no step to count in."""
    uneven = demand(FULL, FULL, FULL)
    uneven.index = pd.DatetimeIndex(["2027-01-01", "2027-01-02", "2027-01-04"], tz="UTC")
    for frame in (demand(FULL), uneven):
        with raises(gm.errors.ValidationError, "invalid_value", match="constant step"):
            gm.schedule(plant_of_two(), frame, RULES | {"operating_time": rule})


def test_operating_days_is_no_rule_any_more():
    """The old name is an unknown rule."""
    with raises(gm.errors.ValidationError, "unknown_name"):
        gm.schedule(plant_of_two(), demand(FULL), RULES | {"operating_days": 3})


def test_an_hourly_demand_is_planned_and_run():
    """Four days of hours: the same plan columns, one row per hour, and a run of them."""
    plant = plant_of_two()
    heat = [(0.5 + 0.1 * (hour % 24) / 24) * FULL for hour in range(96)]
    plan = gm.schedule(plant, demand(*heat, freq="h"), RULES | {"operating_time": "90 h"})
    assert len(plan) == 96 and plan.index[1] - plan.index[0] == pd.Timedelta(hours=1)
    assert plan["d0.is_running"].sum() == plan["d1.is_running"].sum() == 90
    results = gm.simulate(plant, plan)
    assert results.errors() == []
    checks = gm.checks.operating_time(plant, results, "90 h")
    assert [item["passed"] for item in checks] == [True, True]


def test_the_operating_time_is_the_same_fraction_on_hourly_and_daily_steps():
    """Two thirds of three days: 2 days of 3, or 48 hours of 72."""
    low_high = [FULL, 3 * FULL, 2 * FULL]
    daily = gm.schedule(plant_of_two(), demand(*low_high), RULES | {"operating_time": "2 d"})
    hourly = gm.schedule(
        plant_of_two(),
        demand(*np.repeat(low_high, 24), freq="h"),
        RULES | {"operating_time": "48 h"},
    )
    assert daily["d0.is_running"].mean() == hourly["d0.is_running"].mean() == pytest.approx(2 / 3)
    fraction = gm.schedule(plant_of_two(), demand(*low_high), RULES | {"operating_time": 2 / 3})
    pd.testing.assert_frame_equal(fraction, daily, check_freq=False)


def test_a_duration_that_is_not_whole_steps_rounds_to_the_nearest_step():
    """Eight and a half hours of ten runs nine; 8.4 runs eight."""
    heat = demand(*range(1, 11), freq="h") * FULL
    nine = gm.schedule(plant_of_two(), heat, RULES | {"operating_time": "8.5 h"})
    eight = gm.schedule(plant_of_two(), heat, RULES | {"operating_time": "8.4 h"})
    assert nine["d0.is_running"].sum() == 9 and eight["d0.is_running"].sum() == 8


def test_a_fraction_of_the_period_runs_that_share_of_the_steps():
    """Half of six steps is three, one is all of them."""
    heat = demand(*[FULL] * 6)
    for fraction, running in ((0.5, 3), (1, 6)):
        plan = gm.schedule(plant_of_two(), heat, RULES | {"operating_time": fraction})
        assert len(plan.attrs["outages"]["d0"]) == 6 - running


def test_outages_are_dates_or_intervals_of_whole_steps():
    """A date is its whole UTC day, an interval runs from its start up to its end."""
    heat = demand(*[FULL] * 48, freq="h")
    rule = [
        "2027-01-01",
        {"start": "2027-01-02T03:00:00Z", "end": "2027-01-02T05:00:00Z"},
        {"start": "2027-01-02T10:30:00Z", "end": "2027-01-02T11:30:00Z"},
    ]
    plan = gm.schedule(plant_of_two(), heat, RULES | {"operating_time": rule})
    off = plan.attrs["outages"]["d0"]
    assert off[:24] == [at(1, hour) for hour in range(24)]
    assert off[24:] == [at(2, 3), at(2, 4), at(2, 11)]
    assert plan.attrs["outages"]["d1"] == off
    assert plan["d0.flow"].iloc[4] == 0 and plan["d0.flow"].iloc[24] > 0


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
    plan = gm.schedule(plant, demand(0.5 * FULL, FULL, 2 * FULL), RULES | {"operating_time": "2 d"})
    return plan, gm.simulate(plant, plan).to_frame()


def test_a_heat_pump_on_the_brine_of_one_doublet_stops_with_it(split_run):
    """The wiring decides: ``d0`` off stops the heat pump, ``d1`` off does not."""
    plan, frame = split_run
    assert plan["heat_pump.is_running"].tolist() == [False, True, True]
    assert frame["heat_pump.is_running"].iloc[0] == 0 and frame["heat_pump.is_running"].iloc[1] == 1


def test_a_stopped_heat_pump_covers_nothing_before_geothermal():
    """Ordered first, its capacity counts only on the days it runs."""
    rules = RULES | {"order": ["heat_pump", "geothermal", "boiler"], "operating_time": "2 d"}
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


def test_a_finished_run_ran_the_time_of_the_rule():
    """Two doublets, three days of four each: the plan, the run and the check agree."""
    plant = plant_of_two()
    frame = demand(0.5 * FULL, 1.5 * FULL, 2.5 * FULL, 3.0 * FULL)
    results = gm.simulate(plant, gm.schedule(plant, frame, RULES | {"operating_time": "3 d"}))
    assert results.errors() == []
    checks = gm.checks.operating_time(plant, results, "3 d")
    assert [item["passed"] for item in checks] == [True, True]
    assert [item["value"]["value"] for item in checks] == [3 * 86400.0] * 2


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


def sample_demand():
    """Return the daily heating and cooling demand of the sample problem."""
    heat, cool = ("GEMINI_Heating_Demand_Daily_2027.csv", "GEMINI_Cooling_Demand_Daily_2027.csv")
    return pd.concat(
        [
            gm.profiles.from_csv(
                HACKATHON_2027 / heat, {"heating_demand_MWth": "heating_demand"}, "MW"
            ),
            gm.profiles.from_csv(
                HACKATHON_2027 / cool, {"cooling_demand_MWcool": "cooling_demand"}, "MW"
            ),
        ],
        axis=1,
    )


def test_the_bypass_keeps_the_supply_at_the_setpoint_and_delivers_the_demand():
    """Three summer days with a bypass: drive water passes the users, not through them."""
    plant = treatment_plant()
    days = sample_demand().loc["2027-07-18":"2027-07-20"]
    plan = gm.schedule(plant, days, RULES)
    assert plan["loads.split_fraction"].min() > 0
    results = gm.simulate(plant, plan, clock=gm.Clock(days.index, step="24h"))
    supply = results.get("heat_users", "supply_in.temperature")["value"]
    assert min(supply) == pytest.approx(373.15, abs=1e-6)
    totals = gm.kpi.totals(plant, results)
    assert totals["heat_delivered"]["value"] == pytest.approx(
        days["heating_demand"].sum() * 86400, rel=1e-9
    )
    assert totals["heat_surplus"]["value"] == pytest.approx(0, abs=1e-3)


def test_a_plan_states_its_units_so_a_binding_in_another_unit_does_not_misread_it():
    """A binding that reads the rate in m3/s meets a column in kg/s: the plan's unit wins."""
    plant = plant_of_two()
    plant.set_bindings("d0.reservoir", {"production_rate": {"column": "rate", "unit": "m3/s"}})
    plan = gm.schedule(plant, demand(0.5 * FULL), RULES).rename(
        columns={"d0.reservoir.production_rate": "rate"}
    )
    assert plan.attrs["units"]["d1.reservoir.production_rate"] == "kg/s"
    plan.attrs["units"]["rate"] = "kg/s"
    results = gm.simulate(plant, plan)
    flow = results.get("d0.reservoir", "liquid_flow")["value"][0]
    assert flow == pytest.approx(150 / 3600)


def test_a_plan_keeps_the_unit_of_the_demand():
    """What the demand stated stays, and every driven column adds its own."""
    frame = demand(FULL)
    frame.attrs["units"] = {"heating_demand": "W"}
    plan = gm.schedule(plant_of_two(), frame, RULES)
    assert plan.attrs["units"]["heating_demand"] == "W"
    assert plan.attrs["units"]["d0.esp.frequency"] == "Hz"
    assert plan.attrs["units"]["boiler.temperature_setpoint"] == "K"


def test_the_doublet_heat_plant_runs_a_plan_within_its_pump_curve():
    """Its bindings read m3/s and a plan is in kg/s: the flow is what was planned, in range."""
    plant = gm.plants.example("DoubletHeatPlant")
    rules = RULES | {"doublet_flow": {"min": "50 m3/h", "max": "165 m3/h"}}
    results = gm.simulate(plant, gm.schedule(plant, demand(5e6, 3e7), rules), on_error="record")
    assert results.errors() == []
    flows = results.get("doublet.reservoir", "liquid_flow")["value"]
    assert 50 / 3600 <= min(flows) and max(flows) == pytest.approx(165 / 3600)


@pytest.mark.parametrize(
    ("rules", "path"),
    [
        (RULES | {"doublet_flow": None}, "doublet_flow"),
        (RULES | {"doublet_flow": {"max": "300 m3/h"}}, "doublet_flow.min"),
        (RULES | {"doublet_flow": {"min": "50 m3/h"}}, "doublet_flow.max"),
        ({"doublet_flow": RULES["doublet_flow"]}, "max_brine_cooling"),
    ],
)
def test_a_limit_the_schedule_needs_has_no_default(rules, path):
    """No rule is assumed: the missing one is named."""
    with raises(gm.errors.ValidationError, "missing_value") as refused:
        gm.schedule(plant_of_two(), demand(FULL), rules)
    assert refused.value.path == f"rules.{path}"
