"""Unit conversion round trips and historical scale factors."""

from types import SimpleNamespace

import pytest

from gemini.core.physics import units
from gemini.errors import UnitError


@pytest.mark.parametrize(
    "forward,inverse",
    [
        ("bar_to_pa", "pa_to_bar"),
        ("c_to_k", "k_to_c"),
        ("m3h_to_m3s", "m3s_to_m3h"),
        ("md_to_m2", "m2_to_md"),
        ("m3s_to_bbl_per_day", "bbl_per_day_to_m3s"),
        ("ft_head_to_pa", "pa_to_ft_head"),
        ("bhp_to_w", "w_to_bhp"),
        ("m_to_ft", "ft_to_m"),
        ("kgm3_to_lbmft3", "lbmft3_to_kgm3"),
        ("pas_to_cp", "cp_to_pas"),
        ("nm_to_dyne_cm", "dyne_cm_to_nm"),
        ("index_to_si", "index_from_si"),
        ("inch_to_m", "m_to_inch"),
        ("m_to_mm", "mm_to_m"),
        ("m3s_to_m3day", "m3day_to_m3s"),
        ("kgm3_to_mgl", "mgl_to_kgm3"),
        ("pa_to_gpa", "gpa_to_pa"),
        ("rad_to_deg", "deg_to_rad"),
    ],
)
def test_round_trip(forward, inverse):
    """Conversions round-trip a nontrivial input without changing its physical value."""
    assert getattr(units, inverse)(getattr(units, forward)(3.7)) == pytest.approx(3.7)


def test_known_scales():
    """Pressure, temperature and time scales match SI definitions and the legacy year."""
    assert units.bar_to_pa(1) == 100000
    assert units.c_to_k(0) == 273.15
    assert units.SECONDS_PER_YEAR == 31557600


def test_to_si_scales_offsets_and_unknown_units():
    """Raw data units convert with their scale and offset; unknown units name the valid ones."""
    assert units.to_si(2, "bar") == 2e5
    assert units.to_si(1, "barg") == 201325
    assert units.to_si(25, "°C") == 298.15
    assert units.to_si(36, "t/h") == 10
    with pytest.raises(UnitError, match="'barr'.*did you mean 'bar'"):
        units.to_si(1, "barr")


def test_convert_between_units_of_one_dimension():
    """Conversion goes through SI and rejects units of another dimension."""
    assert units.convert(2e5, "Pa", "bar") == 2
    assert units.convert(300, "K", "degC") == pytest.approx(26.85)
    assert units.convert(1, "m3/s", "m3/h") == 3600
    with pytest.raises(UnitError, match="'K'.*'Pa'.*'bar'"):
        units.convert(1, "bar", "K")


def test_convert_identity_for_every_declared_unit():
    """Every unit a quantity alias declares converts to itself."""
    for unit in ("W/K", "Hz", "kg/m3", "Pa.s", "m2", "m/s", "currency", "currency/year"):
        assert units.convert(5.0, unit, unit) == 5.0
    assert units.convert(36.0, "currency/h", "currency/s") == pytest.approx(0.01)
    assert units.convert(5.0, "stages", "stages") == 5.0


def test_difference_quantities_ignore_offsets():
    """A temperature or pressure difference converts by scale only (10 K is 10 degC)."""
    assert units.convert(10.0, "K", "degC", quantity="temperature_difference") == 10.0
    assert units.convert(1e5, "Pa", "barg", quantity="pressure_difference") == 1.0
    assert units.value_in_si("5 degC", "K", "dT", quantity="temperature_difference") == 5.0
    assert units.value_in_si("2 barg", "Pa", "dp", quantity="pressure_difference") == 2e5
    assert units.value_in_si("5 degC", "K", "T", quantity="temperature") == 278.15


def test_value_in_si_parses_strings_and_quantities():
    """Unit strings and Quantity values convert; other values pass through unchanged."""
    assert units.value_in_si("1.5e3 bar", "Pa") == 1.5e8
    assert units.value_in_si(units.Quantity(3, "ft"), "m") == pytest.approx(0.9144)
    assert units.value_in_si("12", "m") == "12"
    with pytest.raises(UnitError, match="plant.length: unit = 'bar'; expected a unit of 'm'"):
        units.value_in_si("12 bar", "m", "plant.length")


def test_value_in_si_without_declared_unit_keeps_the_value():
    """A declaration without a unit keeps text such as '12 m' or '2 stages' unchanged."""
    assert units.value_in_si("12 m", None) == "12 m"
    assert units.value_in_si("2 stages", None) == "2 stages"


def test_value_in_si_only_converts_quantity_objects():
    """Objects that merely carry value and unit attributes are not quantities."""
    duck = SimpleNamespace(value=3, unit="ft")
    assert units.value_in_si(duck, "m") is duck
