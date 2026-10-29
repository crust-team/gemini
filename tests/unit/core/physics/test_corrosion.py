"""CO2 corrosion correlations: goldens, pinned bits, published references and input domain."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from gemini.core.physics import corrosion, units
from gemini.errors import MissingChemistryError, PhysicsRangeError, UnknownCorrelationError

GOLDEN = json.loads((Path(__file__).parents[3] / "fixtures/golden_values.json").read_text())

PINNED_CONDITIONS = dict(
    pressure=units.bar_to_pa(3),
    water_flow_rate=0.011574,
    water_density=1024,
    water_viscosity=5.469e-4,
    diameter=0.1778,
    roughness=2e-5,
    co2_fraction=0.1,
)


@pytest.mark.parametrize("name", [k for k in GOLDEN if k.startswith("corrosion_")])
def test_corrosion_golden(name):
    """All six SI correlation boundaries reproduce original unit-based results."""
    case = GOLDEN[name]
    u, p = case["inputs"], case["parameters"]
    actual = corrosion.co2_corrosion_rate(
        p["corrosion_model"],
        fitted=name.endswith("True"),
        temperature=units.c_to_k(u["temperature"]),
        pressure=units.bar_to_pa(u["pressure"]),
        water_flow_rate=u["flow_rate"],
        water_density=u["water_density"],
        water_viscosity=units.cp_to_pas(u["water_viscosity"]),
        diameter=p["diameter"],
        roughness=p["roughness"],
        co2_fraction=u["co2_fraction"],
        bicarb_concentration=units.mgl_to_kgm3(u["bicarb_concentration"]),
        ionic_strength=u["ionic_strength"],
    )
    assert actual == pytest.approx(case["expected"]["corrosion_rate"], rel=1e-9, abs=0)


@pytest.mark.parametrize(
    "model,celsius,expected",
    [
        ("NORSOK", 5, "0x1.39ef6bb1d37b4p-4"),
        ("NORSOK", 39.999, "0x1.240fcd97dedbcp+4"),
        ("NORSOK", 40, "0x1.092d9caf59908p+0"),
        ("NORSOK", 40.001, "0x1.24124bce0d1e7p+4"),
        ("NORSOK", 50, "0x1.412a3d949fb8ap+4"),
        ("NORSOK", 90, "0x1.004aeaa323c4ap-3"),
        ("NORSOK", 150, "0x1.56035bc15bbccp+3"),
        ("NORSOK", 160, "0x1.561d97dafe0efp+3"),
        ("DLM", 5, "0x1.96c62ef6721c6p-3"),
        ("DLM", 40.001, "0x1.f01765ae47e6ep-1"),
        ("DLM", 160, "0x1.2216f8c7d8747p+2"),
        ("DLD", 5, "0x1.f3e05fdf33386p-2"),
        ("DLD", 40.001, "0x1.106aa3c5935dep-1"),
        ("DLD", 160, "0x1.0e5982cf02bb3p-4"),
    ],
)
def test_pinned_bits_on_and_off_the_temperature_table(model, celsius, expected):
    """Rates keep the exact bits of the original classes, including off-grid temperatures.

    NORSOK has a pH factor only at exactly tabulated temperatures (retained decision): the
    rate at 40 degC is about 1.04 mm/year and about 18.25 mm/year 0.001 degC either side.
    """
    for fitted in (False, True):
        rate = corrosion.co2_corrosion_rate(
            model, fitted=fitted, temperature=units.c_to_k(celsius), **PINNED_CONDITIONS
        )
        assert rate.hex() == expected


@pytest.mark.parametrize(
    "model,coefficients,expected",
    [
        ("NORSOK", {"A": 1.3}, "0x1.58bb4bb0c13bfp+0"),
        ("DLM", {"A": 5.5, "B": 1650, "C": 0.7}, "0x1.74ae0dfc24d21p-1"),
        ("DLD", {"A": 5.0, "B": 1100, "C": 0.6, "D": 2.0}, "0x1.c4ecafaf58582p-2"),
    ],
)
def test_fitted_coefficients_apply_only_to_fitted_models(model, coefficients, expected):
    """Fitted variants use supplied constants; published variants ignore them."""
    conditions = dict(PINNED_CONDITIONS, temperature=units.c_to_k(40), coefficients=coefficients)
    fitted = corrosion.co2_corrosion_rate(model, fitted=True, **conditions)
    published = corrosion.co2_corrosion_rate(model, **conditions)
    assert fitted.hex() == expected
    assert published == corrosion.co2_corrosion_rate(
        model, temperature=units.c_to_k(40), **PINNED_CONDITIONS
    )


@pytest.mark.parametrize("model,expected", [("DLM", 6.7), ("DLD", 9.6)])
@pytest.mark.parametrize("fitted", [False, True])
def test_original_reference(model, expected, fitted):
    """Retain the original tests at 50 degC and 3 bar (de Waard–Lotz 1991/1995)."""
    value = corrosion.co2_corrosion_rate(
        model,
        fitted=fitted,
        temperature=units.c_to_k(50),
        pressure=units.bar_to_pa(3),
        co2_fraction=1,
        water_flow_rate=math.pi * 0.1**2 / 4,
        diameter=0.1,
    )
    assert value == pytest.approx(expected, abs=0.05)


def test_partial_pressure_and_unknown_model():
    """Explicit CO2 partial pressure equals fraction times total pressure."""
    common = dict(temperature=313.15, pressure=300000, water_flow_rate=0.01)
    a = corrosion.co2_corrosion_rate("DLM", co2_fraction=0.1, **common)
    b = corrosion.co2_corrosion_rate("DLM", co2_partial_pressure=30000, **common)
    assert a == pytest.approx(b, rel=1e-12)
    with pytest.raises(UnknownCorrelationError, match="'NORSK'.*did you mean 'NORSOK'"):
        corrosion.co2_corrosion_rate("NORSK", co2_fraction=0.1, **common)
    with pytest.raises(MissingChemistryError, match="co2_fraction"):
        corrosion.co2_corrosion_rate("DLM", **common)


@pytest.mark.parametrize("model", ["NORSOK", "DLD"])
def test_zero_flow_is_outside_flow_dependent_correlations(model):
    """NORSOK and DLD divide by the flow velocity; formerly ZeroDivisionError."""
    with pytest.raises(PhysicsRangeError, match="water_flow_rate = 0"):
        corrosion.co2_corrosion_rate(
            model, temperature=330, pressure=3e5, water_flow_rate=0, co2_fraction=0.1
        )
    assert (
        corrosion.co2_corrosion_rate(
            "DLM", temperature=330, pressure=3e5, water_flow_rate=0, co2_fraction=0.1
        )
        > 0
    )


@pytest.mark.parametrize("model", ["NORSOK", "DLM", "DLD"])
@pytest.mark.parametrize("chemistry", [{"co2_fraction": 0}, {"co2_partial_pressure": 0}])
def test_zero_co2_is_outside_the_correlations(model, chemistry):
    """The correlations take the logarithm of the CO2 fugacity; formerly a math error."""
    with pytest.raises(PhysicsRangeError, match="CO2 partial pressure = 0"):
        corrosion.co2_corrosion_rate(
            model, temperature=330, pressure=3e5, water_flow_rate=0.01, **chemistry
        )


def test_negative_flow_with_a_complex_rate_is_rejected():
    """A negative DLD velocity makes the rate complex; formerly TypeError from float()."""
    with pytest.raises(PhysicsRangeError, match="complex rate"):
        corrosion.co2_corrosion_rate(
            "DLD", temperature=330, pressure=3e5, water_flow_rate=-0.01, co2_fraction=0.1
        )


def test_ph_factor_table_segments_and_fallback():
    """Tabulated segments include their upper bound; other temperatures and pH give 7."""
    assert corrosion._ph_factor(40.0, 4.6) == 2.0676 - 0.2309 * 4.6
    assert corrosion._ph_factor(5.0, 4.0) == 2.0676 + 0.2309 * 4.0
    assert corrosion._ph_factor(90.0, 5.62) == 21254 * math.exp(-2.1811 * 5.62)
    assert corrosion._ph_factor(150.0, 3.5) == 1
    assert corrosion._ph_factor(40.001, 5.0) == 7
    assert corrosion._ph_factor(40.0, 3.49) == 7
    assert corrosion._ph_factor(40.0, 6.51) == 7
    assert corrosion._ph_factor(40.0, float("nan")) == 7


def test_wall_loss():
    """WIMS integration uses interval duration and the original 365.25-day year."""
    np.testing.assert_allclose(
        corrosion.wall_loss([1, 2], [units.SECONDS_PER_YEAR / 2] * 2), [0.5, 1.5]
    )
    with pytest.raises(PhysicsRangeError, match="shape"):
        corrosion.wall_loss([1, 2], [1])
    with pytest.raises(PhysicsRangeError, match="negative"):
        corrosion.wall_loss([1], [-1])


def test_wims_remaining_wall_and_lifetime():
    """WIMS radial loss and linear lifetime retain deposition and missing-data limits."""
    assert corrosion.remaining_wall_thickness(0.1, 0.09, 0.002) == pytest.approx(0.008)
    assert corrosion.remaining_wall_thickness(0.1, 0.09, -0.002) == pytest.approx(0.012)
    assert corrosion.time_to_minimum_wall(0.008, 0.006, 1e-10) == pytest.approx(2e7)
    assert corrosion.time_to_minimum_wall(0.005, 0.006, 1e-10) == 0
    assert math.isinf(corrosion.time_to_minimum_wall(0.008, 0.006, 0))
    assert math.isnan(corrosion.time_to_minimum_wall(float("nan"), 0.006, 1e-10))
