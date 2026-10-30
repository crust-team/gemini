"""Nodal analysis and the pump curve, against the plant's own calls and hand formulas."""

import copy
import json

import pytest

import gemini as gm
from gemini.analysis import wells
from gemini.core.physics import units
from gemini.core.types.flows import Stream

BAR = 1e5
CASE = {"wellhead_pressure": "4.6 bar", "rates": [20, 45], "frequency": 55.484}


@pytest.fixture(scope="module")
def doublet_curves(shared_plant):
    """Return the nodal analysis of the example doublet at two ESP frequencies."""
    faster = dict(CASE, frequency=58.0)
    return wells.nodal(shared_plant, "doublet", [CASE, faster])


def test_the_operating_point_reproduces_the_wellhead_pressure_in_the_plant_call(
    shared_plant, doublet_curves
):
    """Commanding the solved rate and frequency, the doublet delivers the 4.6 bar asked for."""
    point = doublet_curves["cases"][0]["operating_point"]
    doublet = copy.deepcopy(shared_plant).get_module("doublet")
    doublet.get_module("esp").frequency = CASE["frequency"]
    doublet.get_module("reservoir").production_rate = point["rate"]
    fluid = doublet.get_module("reservoir").fluid
    supply = doublet(return_in=Stream(m_dot=point["rate"], T=300.0, p=1e6, fluid=fluid)).outlets
    assert supply.supply_out.p == pytest.approx(4.6 * BAR, rel=1e-9)
    assert point["wellhead_pressure"] == pytest.approx(4.6 * BAR)


def test_the_lift_curve_falls_with_rate_and_the_inflow_curve_too(doublet_curves):
    """Both curves fall with rate, as the well friction and the drawdown grow."""
    case = doublet_curves["cases"][0]
    for curve in (case["ipr"], case["vlp"]):
        assert len(curve["rate"]) == wells.CURVE_POINTS
        assert curve["pressure"] == sorted(curve["pressure"], reverse=True)


def test_the_inflow_curve_follows_the_linear_productivity_index(shared_plant, doublet_curves):
    """At the first rate, the sandface pressure is reservoir pressure minus flow over index."""
    reservoir = shared_plant.get_module("doublet.reservoir")
    rate = doublet_curves["cases"][0]["ipr"]["rate"][0]
    density = reservoir.fluid.properties(reservoir.pressure, reservoir.temperature).rho_l
    expected = reservoir.pressure - rate / density / reservoir.productivity_index
    assert doublet_curves["cases"][0]["ipr"]["pressure"][0] == pytest.approx(expected, rel=1e-12)


def test_a_higher_frequency_lifts_more(doublet_curves):
    """A what-if at a higher pump frequency gives a higher operating rate."""
    slow, fast = (case["operating_point"]["rate"] for case in doublet_curves["cases"])
    assert fast > slow


def test_the_plant_is_not_changed(shared_plant, doublet_curves):
    """The ESP frequency of a case is set on a copy: the plant's control stays unset."""
    with pytest.raises(gm.errors.MissingValueError):
        shared_plant.get_module("doublet.esp").frequency


def test_a_bracket_outside_the_well_model_fails_that_case_only():
    """Rates up to 200 kg/s drive the pressure below zero: the case carries the error."""
    plant = gm.Plant.load("examples/shared/doublet_heat/plant.json")
    result = wells.nodal(plant, "doublet", [dict(CASE, rates=[20, 200]), CASE])
    broken, fine = result["cases"]
    assert broken["error"]["code"] == "physics_range"
    assert broken["ipr"] is None and broken["operating_point"] is None
    assert fine["operating_point"] is not None


def test_inputs_are_checked(shared_plant):
    """A missing pressure, an unknown path and a path without a reservoir are named."""
    with pytest.raises(gm.errors.ValidationError, match="wellhead_pressure") as missing:
        wells.nodal(shared_plant, "doublet", {"rates": [1, 2], "frequency": 50})
    assert missing.value.code == "missing_value"
    with pytest.raises(gm.errors.UnknownNameError):
        wells.nodal(shared_plant, "doublt", CASE)
    with pytest.raises(gm.errors.ValidationError, match="ProductionReservoir"):
        wells.nodal(shared_plant, "doublet.esp", CASE)


def test_an_injection_chain_is_not_solved_yet(shared_plant):
    """The injection side names itself as not implemented."""
    with pytest.raises(gm.errors.NotImplementedYet, match="injection"):
        wells.nodal(shared_plant, "doublet.sink", CASE)


def test_pump_curve_starts_at_the_shut_in_head_of_the_polynomial(shared_plant):
    """At zero flow and 60 Hz the head is the first coefficient times the stages, in Pa."""
    pump = shared_plant.get_module("doublet.esp")
    curve = wells.pump_curve(shared_plant, "doublet.esp")
    expected = units.ft_head_to_pa(pump.head_coeff[0] * pump.no_stages)
    assert curve["curve"]["flow"][0] == 0.0
    assert curve["curve"]["head"][0] == pytest.approx(expected, rel=1e-12)
    assert curve["frequency"] == 60.0
    assert curve["measured"] == [] and curve["correction"] is None


def test_pump_curve_recovers_a_known_correction(shared_plant):
    """Points measured at 0.9 times the model head plus 1 kPa give the inverse line back."""
    pump = shared_plant.get_module("doublet.esp")
    points = [
        {"flow": flow, "frequency": 55.0, "head": 0.9 * pump.head_function(flow, 55.0) + 1000}
        for flow in (0.02, 0.03, 0.04)
    ]
    curve = wells.pump_curve(shared_plant, "doublet.esp", points)
    assert curve["correction"]["slope"] == pytest.approx(1 / 0.9, rel=1e-9)
    assert curve["correction"]["offset"] == pytest.approx(-1000 / 0.9, rel=1e-9)
    assert curve["measured"][0]["theoretical_head"] == pump.head_function(0.02, 55.0)


def test_pump_curve_with_one_point_has_no_correction_and_says_why(shared_plant):
    """One point cannot fix a line; unit strings are read."""
    point = {"flow": "150 m3/h", "frequency": "55 Hz", "head": "20 bar"}
    curve = wells.pump_curve(shared_plant, "doublet.esp", [point])
    assert curve["correction"] is None
    assert "two or more" in curve["reason"]
    assert curve["measured"][0]["flow"] == pytest.approx(150 / 3600)
    assert curve["measured"][0]["head"] == 20 * BAR
    json.dumps(curve, allow_nan=False)


def test_pump_curve_needs_an_esp(shared_plant):
    """A path that is not an ESP is refused."""
    with pytest.raises(gm.errors.ValidationError, match="ESP"):
        wells.pump_curve(shared_plant, "doublet.well")


def test_injectivity_and_pump_calibration_are_not_built_yet():
    """Both keep their final signature and say so."""
    with pytest.raises(gm.errors.NotImplementedYet):
        wells.injectivity(None, "doublet.injector")
    with pytest.raises(gm.errors.NotImplementedYet):
        wells.calibrate_pump(None, "doublet.esp", None)
