"""Every public return of ``api.md`` fits the three shapes, on the doublet example."""

import copy
import json
import re

import pytest

import gemini as gm
from tests.fixtures import ROOT
from tests.fixtures.costed_plants import cooling_plant, day, heating_plant
from tests.fixtures.json_schema import check

SCHEMAS = ROOT / "docs" / "schemas"
PAGE = ROOT / ".claude" / "docs" / "api.md"
CASE = {"wellhead_pressure": "4.6 bar", "rates": [20, 45], "frequency": 55.484}
BROKEN = dict(CASE, rates=[20, 200])
CORROSION = {
    "correlation": "NORSOK",
    "conditions": {
        "temperature": "60 degC",
        "pressure": "20 bar",
        "water_flow_rate": 0.01,
        "co2_partial_pressure": "2 bar",
        "diameter": 0.1,
    },
    "thickness": 0.008,
    "minimum_thickness": 0.005,
    "start": "2024-01-01T00:00:00Z",
}
VALUES = gm.economics.Assumptions(
    electricity_price=2e-8,
    heat_price=5e-8,
    cold_price=4e-8,
    electricity_emission_factor=1e-7,
)
POINTS = [
    {"flow": 0.03, "frequency": 50, "head": 3e6},
    {"flow": 0.04, "frequency": 50, "head": 2.5e6},
]
HEADS = [9e6, 8.9e6, 8.7e6, 8.2e6, 7.5e6, 6.5e6, 5e6]
UNSHAPED = {"skip_counts", "reasons", "end_state", "conditions"}
"""Keys of a return that hold tallies or the input of a next call, not values."""

RETIRED = {"values", "units", "tolerance", "timestamp", "class", "type", "module"}
"""Keys of the former shapes; none is in a public return."""


def _limits():
    return gm.checks.Limits().add("heat_exchanger.duty", min="0 MW")


def _run_entries(plant, results):
    return {
        "evaluate": lambda: gm.evaluate(
            "HeatExchanger",
            {
                "thermal_conductance": 5e5,
                "hot_nominal_pressure_drop": 1e4,
                "cold_nominal_pressure_drop": 1e4,
                "hot_nominal_mass_flow": 40,
                "cold_nominal_mass_flow": 40,
            },
            {
                "hot_in": {"m_dot": 40.0, "T": "90 degC", "p": "5 bar"},
                "cold_in": {"m_dot": 40.0, "T": "40 degC", "p": "5 bar"},
            },
            {},
        ),
        "evaluate.record": lambda: gm.evaluate("Boilr", {}, {}, {}, on_error="record"),
        "get": lambda: results.get("heat_exchanger", "duty"),
        "summary": results.summary,
        "errors": results.errors,
        "to_dict": results.to_dict,
        "energy_report": results.energy_report,
    }


def _analysis_entries(plant):
    return {
        "nodal": lambda: gm.analysis.nodal(plant, "doublet", [CASE, BROKEN], on_error="record"),
        "pump_curve": lambda: gm.analysis.pump_curve(plant, "doublet.esp", POINTS),
        "corrosion_forecast": lambda: gm.analysis.corrosion_forecast(CORROSION, "2026-01-01"),
        "fit_head_coefficients": lambda: gm.analysis.fit_head_coefficients(
            [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07], [50] * 7, HEADS, 10
        ),
        "fit_head_correction": lambda: gm.analysis.fit_head_correction(
            [1e6, 2e6, 3e6], [1.1e6, 2.3e6, 3.2e6]
        ),
        "estimate_reservoir_pressure": lambda: gm.analysis.estimate_reservoir_pressure(
            [0.01, 0.02, 0.03], [2e7, 1.9e7, 1.81e7]
        ),
        "estimate_conductance": lambda: gm.analysis.estimate_conductance(
            350, 320, 300, 330, 10, 10
        ),
    }


def _economics_entries():
    costed, run = heating_plant(), day()
    cold, chilled = cooling_plant(), day(heat=None, cold=500.0)
    return {
        "capex": lambda: gm.economics.capex(costed),
        "opex": lambda: gm.economics.opex(costed, run, VALUES),
        "lcoh": lambda: gm.economics.lcoh(costed, run, 0.05, 20, VALUES),
        "lcoc": lambda: gm.economics.lcoc(cold, chilled, 0.05, 20, VALUES),
        "co2": lambda: gm.economics.co2(costed, run, VALUES),
        "npv": lambda: gm.economics.npv(costed, run, 0.05, 20, VALUES),
        "payback": lambda: gm.economics.payback(costed, run, VALUES),
        "economics.record": lambda: gm.economics.lcoh(
            heating_plant(costed=False), run, 0.05, 20, VALUES, on_error="record"
        ),
    }


def _ledger_entries(plant, results):
    return {
        "compute": lambda: gm.kpi.compute(plant, results),
        "totals": lambda: gm.kpi.totals(plant, results),
        "energy_balance": lambda: gm.checks.energy_balance(results),
        "mass_balance": lambda: gm.checks.mass_balance(results),
        "bounds": lambda: gm.checks.bounds(plant, results),
        "plant_balance": lambda: gm.checks.plant_balance(plant, results),
        "limits": lambda: gm.checks.limits(plant, results, _limits()),
        "run_all": lambda: gm.checks.run_all(plant, results),
        "Limits": lambda: _limits().to_dict(),
    }


def _validation_entries(plant):
    return {
        "validate_params": lambda: gm.modules.Valve.validate_params({"nope": 1}, on_error="record"),
        "plants.validate": lambda: gm.plants.validate({"format": 2, "name": 3}, on_error="record"),
        "p.validate": lambda: plant.validate(on_error="record"),
        "to_dict": lambda: [gm.errors.ValidationError("bad", code="invalid_unit").to_dict()],
    }


@pytest.fixture(scope="module")
def plant():
    """Give the example plant, not shared with tests that mutate it."""
    return gm.plants.example("DoubletHeatPlant")


@pytest.fixture(scope="module")
def results(plant, fast_dataset):
    """Give a replay of six hours, with one failed row and one skipped row."""
    frame = fast_dataset.window(None, "2024-07-01T06:00:00Z").to_frame()
    frame.iloc[2, frame.columns.get_loc("doublet.esp.frequency")] = -5.0
    frame.iloc[4, frame.columns.get_loc("doublet.esp.frequency")] = float("nan")
    units = {name: info.model_dump() for name, info in fast_dataset.columns.items()}
    return gm.replay(copy.deepcopy(plant), gm.Dataset(frame, units=units), on_error="record")


@pytest.fixture(scope="module")
def entries(plant, results):
    """Give ``{name: call}`` of every entry of the page that returns data."""
    return (
        _run_entries(plant, results)
        | _analysis_entries(plant)
        | _economics_entries()
        | _ledger_entries(plant, results)
        | {f"problems.{key}": item for key, item in _validation_entries(plant).items()}
    )


def _schema(name):
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text())


def _shape_of(item):
    """Return the name of the shape a dict has, if any."""
    if {"value", "unit"} <= item.keys():
        return "value"
    if {"path", "code", "message", "suggestions"} <= item.keys():
        return "problem"
    if {"name", "passed", "value", "limit"} <= item.keys():
        return "check"
    return None


def _walk(tree, where="$"):
    """Yield ``(where, problem)`` for each shape of a return that breaks a rule."""
    if isinstance(tree, list):
        for index, item in enumerate(tree):
            yield from _walk(item, f"{where}[{index}]")
        return
    if isinstance(tree, bool) or tree is None or isinstance(tree, str):
        return
    if isinstance(tree, (int, float)):
        yield where, "a bare number has no unit"
        return
    yield from _walk_mapping(tree, where)


def _walk_mapping(tree, where):
    for key in RETIRED & tree.keys():
        yield where, f"the former key {key!r}"
    shape = _shape_of(tree)
    if shape is not None:
        for problem in check(tree, _schema(shape)):
            yield where, problem
    for key, item in tree.items():
        if key in UNSHAPED or (shape == "value" and key in ("value", "time")):
            continue
        if shape == "problem":
            continue
        yield from _walk(item, f"{where}.{key}")


def _walked(entries):
    return [(name, call()) for name, call in entries.items()]


def test_every_public_return_fits_its_shapes(entries):
    """Each dict that has a shape validates against its schema; no number travels alone."""
    found = [
        (name, where, problem)
        for name, result in _walked(entries)
        for where, problem in _walk(result)
    ]
    assert found == []


def test_the_walk_meets_every_shape(entries):
    """A walk that meets no shape proves nothing: a null value, a problem and a check are seen."""
    results = dict(_walked(entries))
    assert results["economics.record"]["reason"]
    assert results["nodal"]["cases"][1]["error"]["code"] == "out_of_range"
    assert results["bounds"]["limit"] == {"value": 0, "unit": "-"}
    assert any("time" in row for row in results["errors"])
    assert {row["code"] for row in results["errors"]} >= {"missing_value"}


def test_the_walker_finds_a_broken_return():
    """A checker that accepts everything proves nothing."""
    assert list(_walk({"value": None, "unit": "W"}))
    assert list(_walk({"head": 3.0}))
    assert list(_walk({"values": [], "unit": "W"}))


def test_every_data_entry_of_the_page_is_walked(entries):
    """A new name of ``analysis``, ``economics``, ``kpi`` or ``checks`` joins the walk."""
    page = PAGE.read_text()
    listed = set(re.findall(r"gm\.(?:analysis|economics|kpi|checks)\.(\w+)\(", page))
    listed |= set(re.findall(r"`(mass_balance|bounds)\(", page))
    later = {"injectivity", "calibrate_pump", "calibrate_corrosion", "erosion", "names"}
    assert listed - later <= entries.keys()


def test_each_shape_is_in_the_page(entries):
    """The page names the schemas the walk validates against."""
    page = PAGE.read_text()
    assert all(f"`{name}`" in page for name in ("value", "problem", "check"))
