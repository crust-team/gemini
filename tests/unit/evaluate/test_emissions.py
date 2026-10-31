"""CO2 of a run against the balance code and a hand sum."""

import pytest

import gemini as gm
from gemini.runtime import settings
from tests.fixtures.costed_plants import HOURS, day, heating_plant
from tests.fixtures.parity import BACKENDS
from tests.fixtures.result_tables import make_results

DAY = HOURS * 3600.0
"""Seconds of the runs below."""

ELECTRICITY = gm.Assumptions(electricity_emission_factor=1e-7)
"""A grid emission factor [kg/J] for runs that draw electricity."""


def test_co2_sums_the_emission_outputs_and_grid_electricity():
    """1 kg/s of CO2, 0.1 kg/s of methane and 60 W of grid electricity for a day."""
    values = gm.Assumptions(electricity_emission_factor=1e-7)
    run = make_results(
        {
            "air": {"co2_emission": [1.0] * HOURS, "methane_emission": [0.1] * HOURS},
            "grid": {"net_import": [60.0] * HOURS},
        }
    )
    result = gm.evaluate.co2(heating_plant(), run, values)
    assert result["unit"] == "kg"
    assert result["direct"] == {"value": DAY, "unit": "kg"}
    assert result["methane"]["value"] == pytest.approx(0.1 * DAY)
    assert result["grid_energy"] == {"value": 60.0 * DAY, "unit": "J"}
    assert result["electricity"]["value"] == pytest.approx(60.0 * DAY * 1e-7)
    assert result["value"] == pytest.approx(DAY + 0.1 * DAY * 29.8 + 60.0 * DAY * 1e-7)
    assert result["window"] == {"value": DAY, "unit": "s"}


def test_the_methane_factor_is_an_assumption():
    """``methane_gwp`` scales the methane released."""
    run = make_results({"air": {"methane_emission": [1.0]}})
    values = gm.Assumptions(methane_gwp=10.0)
    assert gm.evaluate.co2(heating_plant(), run, values)["value"] == pytest.approx(36000.0)


def test_fuel_alone_emits_nothing_of_its_own():
    """Emissions come from the composition through the modules, not from a fuel factor."""
    run = make_results({"boiler": {"fuel": [500.0]}})
    assert gm.evaluate.co2(heating_plant(), run)["value"] == 0
    assert gm.evaluate.co2(heating_plant(), run)["fuel_energy"]["value"] == 500.0 * 3600


def test_the_energies_of_a_run_do_not_depend_on_the_backend():
    """Economics reads the arrays of a finished run under any backend."""
    run = day(electricity=100.0, generated=40.0, fuel=1000.0)
    expected = gm.evaluate.co2(heating_plant(), run, ELECTRICITY)
    for backend in BACKENDS:
        with settings(backend=backend):
            assert gm.evaluate.co2(heating_plant(), run, ELECTRICITY) == expected


def test_a_surplus_of_generation_earns_no_credit():
    """Generation above consumption draws no grid electricity, and the factor is not needed."""
    result = gm.evaluate.co2(heating_plant(), day(electricity=10.0, generated=50.0, fuel=0.0))
    assert result["grid_energy"]["value"] == 0.0
    assert result["value"] == 0.0


def test_grid_electricity_without_a_factor_is_refused():
    """Drawing electricity with no ``electricity_emission_factor`` names what to give."""
    with pytest.raises(gm.errors.ValidationError, match="electricity_emission_factor") as error:
        gm.evaluate.co2(heating_plant(), day())
    assert error.value.code == "missing_assumption"


def test_a_run_without_fuel_or_electricity_emits_nothing():
    """A run without those columns draws nothing."""
    quiet = make_results({"heat": {"unmet_demand": [1.0, 2.0]}})
    result = gm.evaluate.co2(heating_plant(), quiet)
    assert result["fuel_energy"]["value"] == 0.0 and result["grid_energy"]["value"] == 0.0
