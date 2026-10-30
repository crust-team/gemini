"""Energy and mass ledgers of a run: synthetic columns and the example plant."""

import math

import gemini as gm
from tests.fixtures.result_tables import make_results

ENERGY = {"electricity": [10.0, 5.0], "heat_loss": [1.0, 0.5], "heat_accumulation": [-3.0, 2.0]}


def test_energy_ledger_passes_and_reports_the_smallest_power():
    """Signed storage is not judged; the smallest of the other columns is 0.5 W."""
    result = gm.checks.energy_balance(make_results({"leaf": ENERGY}))
    assert result == {"name": "energy_balance", "passed": True, "value": 0.5, "tolerance": 1e-9}


def test_a_negative_nonnegative_output_fails():
    """A heat loss of -2 W breaks the sign convention."""
    result = gm.checks.energy_balance(make_results({"leaf": {"heat_loss": [1.0, -2.0]}}))
    assert result["passed"] is False and result["value"] == -2.0


def test_noise_below_the_tolerance_and_missing_values_are_accepted():
    """-1e-12 W is zero; a NaN tick is a skipped row, not a violation."""
    noisy = make_results({"leaf": {"fuel": [-1e-12, math.nan, 4.0]}})
    assert gm.checks.energy_balance(noisy)["passed"] is True


def test_an_infinite_power_fails():
    """A divergent value is a failure even though it is not negative."""
    result = gm.checks.energy_balance(make_results({"leaf": {"fuel": [1.0, math.inf]}}))
    assert result["passed"] is False


def test_nothing_to_judge_is_undecided_with_a_reason():
    """No energy column, or only missing values, gives ``passed`` None."""
    other = gm.checks.energy_balance(make_results({"leaf": {"head": [1.0]}}))
    assert other["passed"] is None and other["reason"] == "results have no energy output column"
    empty = gm.checks.energy_balance(make_results({"leaf": {"fuel": [math.nan]}}))
    assert empty["passed"] is None and empty["reason"] == "every value is missing"


def test_mass_ledger_reads_the_columns_in_kg_per_second():
    """Only outputs whose unit is kg/s count; the other column is ignored."""
    columns = {"degasser": {"gas_mass_flow": [0.2, 0.0], "pressure_drop": [-5.0, -5.0]}}
    units = {"degasser": {"gas_mass_flow": "kg/s", "pressure_drop": "Pa"}}
    result = gm.checks.mass_balance(make_results(columns, units=units))
    assert result == {"name": "mass_balance", "passed": True, "value": 0.0, "tolerance": 1e-12}
    negative = make_results({"degasser": {"gas_mass_flow": [-0.1]}}, units=units)
    assert gm.checks.mass_balance(negative)["passed"] is False


def test_mass_ledger_without_a_mass_flow_is_undecided():
    """No output in kg/s: nothing to judge."""
    result = gm.checks.mass_balance(make_results({"leaf": {"head": [1.0]}}))
    assert result["passed"] is None and result["reason"] == "results have no output in kg/s"


def test_the_example_plant_run_passes_both_ledgers(fresh_plant, fast_dataset):
    """A six-hour replay of the doublet heat plant has non-negative powers and mass flows."""
    replay = gm.Engine(fresh_plant).replay(fast_dataset.window(None, "2024-07-01T06:00:00Z"))
    assert gm.checks.energy_balance(replay)["passed"] is True
    assert gm.checks.mass_balance(replay)["passed"] is True
