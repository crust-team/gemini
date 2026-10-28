"""Unit conversion round trips and historical scale factors."""

import pytest

from gemini.core.physics import units


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
