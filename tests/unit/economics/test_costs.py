"""Investment and operating cost against the declared costs and hand sums."""

import pytest

import gemini as gm
from gemini.economics import costs
from gemini.modules.pumps import _physics
from gemini.physics.units import SECONDS_PER_YEAR
from tests.fixtures.costed_plants import HOURS, cooling_plant, day, heating_plant
from tests.fixtures.errors import raises
from tests.fixtures.result_tables import make_results

HEAT_PER_YEAR = 1000.0 * SECONDS_PER_YEAR
"""Heat [J/year] of 1000 W delivered all year."""

GRID_PER_YEAR = 100.0 * SECONDS_PER_YEAR
"""Grid electricity [J/year] of 100 W drawn all year."""


def test_capex_is_the_declared_cost_with_its_source():
    """The investment is ``total_cost``'s, in its currency, with year and source."""
    result = gm.economics.capex(heating_plant())
    assert result == {
        "value": 1000.0,
        "unit": "EUR",
        "price_year": {"value": 2024, "unit": "year"},
        "source": "test fixture",
    }


def test_capex_of_a_plant_without_declared_costs_is_null_with_a_reason():
    """Built-in modules declare no cost: nothing is invented."""
    result = gm.economics.capex(heating_plant(costed=False), on_error="record")
    assert result["value"] is None
    assert result["reason"] == costs.NO_COST
    assert result["unit"] == "EUR"
    no_euro = gm.economics.capex(
        heating_plant(costed=False), gm.economics.Assumptions(currency="USD"), on_error="record"
    )
    assert no_euro["unit"] == "USD"


def test_a_factor_without_a_source_is_asked_for(shared_plant):
    """The heat exchanger has no sourced factor: the error names it, the record says why."""
    recorded = gm.economics.capex(shared_plant, on_error="record")
    assert recorded["value"] is None and "exchanger_cost" in recorded["reason"]
    with raises(gm.errors.ValidationError, "missing_assumption", match="exchanger_cost"):
        gm.economics.capex(shared_plant)


COSTS = gm.economics.Assumptions(
    pump_cost=0.5,
    exchanger_cost=100.0,
    chiller_cost=0.3,
    flare_cost=1e5,
    makeup_cost=2e4,
)


def priced(kind, params):
    """Return the capex of one module in a plant of its own, its ports aside."""
    plant = gm.Plant("One")
    plant.add(kind, name="unit", params=params)
    return gm.economics.capex(plant, COSTS)


@pytest.mark.parametrize(
    "kind, params, expected",
    [
        ("HeatPump", {"mode": "heating", "capacity": "10 MW"}, 0.67e7),
        ("Boiler", {"capacity": "10 MW", "efficiency": 0.9}, 0.06e7),
        (
            "CHP",
            {
                "electric_capacity": "1 MW",
                "electric_efficiency": 0.4,
                "thermal_efficiency": 0.45,
                "maximum_outlet_temperature": 363.15,
            },
            0.95e6,
        ),
        ("Degasser", {}, 1.0e6),
        ("Flare", {}, 1e5),
        ("GasMakeup", {}, 2e4),
    ],
    ids=["heat_pump", "boiler", "chp", "degasser", "flare", "makeup"],
)
def test_equipment_costs_come_from_its_design(kind, params, expected):
    """A factor times a capacity, or a fixed item."""
    assert priced(kind, params)["value"] == pytest.approx(expected)


def test_the_exchanger_and_the_chiller_cost_by_their_size():
    """Conductance and capacity."""
    exchanger = dict(
        thermal_conductance=1e6,
        hot_nominal_pressure_drop=0,
        cold_nominal_pressure_drop=0,
        hot_nominal_mass_flow=100.0,
        cold_nominal_mass_flow=100.0,
    )
    assert priced("HeatExchanger", exchanger)["value"] == pytest.approx(1e8)
    chiller = dict(
        mode="chiller",
        capacity=1e7,
        characteristic_slope=7e5,
        minimum_driving_difference=10.0,
        rejection_coefficient=2.2,
        evaporator_coefficient=1.2,
        auxiliary_power_ratio=0.01,
    )
    assert priced("AbsorptionUnit", chiller)["value"] == pytest.approx(3e6)


def test_a_doublet_pays_for_its_wells_and_its_pump():
    """Two wells by the metre; the pump by its shaft power at the nominal flow."""
    design = {
        "depth": "2500 m",
        "gradient": "30 K/km",
        "surface_temperature": "12 degC",
        "permeability": "200 mD",
        "thickness": "100 m",
        "well_diameter": "0.244 m",
    }
    wells = 2 * 2500 * 5.7e6 / (2 * 2300)
    assert priced("Doublet", design)["value"] == pytest.approx(wells)
    pump = {
        "nominal_flow": "300 m3/h",
        "pump_efficiency": 0.7,
        "nominal_wellhead_pressure": "10 bar",
    }
    plant = gm.Plant("One")
    doublet = plant.add("Doublet", name="unit", params=design | pump)
    power = 300 / 3600 * _physics.head(0.0, 60.0, 1, doublet.esp.head_coefficients) / 0.7
    result = gm.economics.capex(plant, COSTS)
    assert result["value"] == pytest.approx(wells + 0.5 * power)
    assert "SDE+" in result["source"] and "assumptions.pump_cost" in result["source"]


def test_a_doublet_without_a_design_declares_no_cost():
    """The old way has no depth to price."""
    assert gm.plants.get("Doublet").capex(COSTS) is None


def test_annual_energies_scale_the_window_to_a_year():
    """A day of 1000 W of heat is 1000 W for a year; 100 W of electricity is all grid."""
    annual = costs.annual_energies(heating_plant(), day())
    assert annual.heat == pytest.approx(HEAT_PER_YEAR, rel=1e-12)
    assert annual.grid == pytest.approx(GRID_PER_YEAR, rel=1e-12)
    assert annual.cold == 0.0 and annual.fuel == 0.0


def test_opex_adds_fixed_variable_and_energy_bill():
    """10 EUR fixed, 1e-9 EUR/J of heat and the electricity at 2e-8 EUR/J."""
    values = gm.economics.Assumptions(electricity_price=2e-8)
    result = gm.economics.opex(heating_plant(), day(), values)
    components = {name: item["value"] for name, item in result["components"].items()}
    assert {item["unit"] for item in result["components"].values()} == {"EUR/year"}
    assert components["fixed"] == 10.0
    assert components["variable"] == pytest.approx(1e-9 * HEAT_PER_YEAR, rel=1e-12)
    assert components["electricity"] == pytest.approx(2e-8 * GRID_PER_YEAR, rel=1e-12)
    assert components["fuel"] == 0.0
    assert result["value"] == pytest.approx(sum(components.values()), rel=1e-12)
    assert result["unit"] == "EUR/year"


def test_opex_needs_the_price_of_an_energy_the_run_draws():
    """Electricity is drawn but has no price: the user is asked, not guessed for."""
    with pytest.raises(gm.errors.ValidationError, match="electricity_price") as error:
        gm.economics.opex(heating_plant(), day())
    assert error.value.code == "missing_assumption"


def test_gas_price_buys_purchased_gas_only():
    """Co-produced gas costs nothing; a price per MWh prices what was purchased."""
    columns = {
        "pump": {"electricity": [0.0] * HOURS},
        "boiler": {"fuel": [3e6] * HOURS, "fuel_purchased": [1e6] * HOURS},
    }
    values = gm.economics.Assumptions(gas_price=40.0)
    annual = costs.annual_energies(heating_plant(), make_results(columns))
    bill = costs._bill(values, annual)
    assert bill["fuel"] == pytest.approx(annual.fuel / 3.6e9 * 40.0)
    assert annual.fuel == pytest.approx(1e6 * SECONDS_PER_YEAR)
    with pytest.raises(gm.errors.ValidationError, match="gas_price") as error:
        costs._bill(gm.economics.Assumptions(), annual)
    assert error.value.code == "missing_assumption"


def test_opex_without_declared_costs_reports_only_the_bill():
    """No declared cost: the value is null and says why; the bill is still given."""
    values = gm.economics.Assumptions(electricity_price=2e-8)
    result = gm.economics.opex(heating_plant(costed=False), day(), values, on_error="record")
    assert result["value"] is None and result["reason"] == costs.NO_COST
    assert result["components"]["electricity"]["value"] == pytest.approx(
        2e-8 * GRID_PER_YEAR, rel=1e-12
    )


def test_opex_refuses_prices_in_another_currency():
    """A cost in EUR and assumptions in USD do not mix."""
    values = gm.economics.Assumptions(electricity_price=2e-8, currency="USD")
    with pytest.raises(gm.errors.ValidationError, match="currency"):
        gm.economics.opex(heating_plant(), day(), values)


def test_cold_is_counted_from_the_cooling_consumers():
    """Cold delivered per year comes from ``heat_absorbed`` of the cooling consumers."""
    annual = costs.annual_energies(cooling_plant(), day(heat=None, cold=300.0))
    assert annual.cold == pytest.approx(300.0 * SECONDS_PER_YEAR, rel=1e-12)
    assert annual.heat == 0.0
