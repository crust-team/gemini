"""TNO pump polynomials on the historical US basis."""

import pytest

from gemini.core.physics import constants, pumps, units


def test_head_and_power_polynomials():
    """Coefficients act on bbl/day and give ft of head or bhp per stage at 60 Hz."""
    flow = units.bbl_per_day_to_m3s(1000)
    assert pumps.head(flow, 60, 1, [10, 0.01]) == pytest.approx(units.ft_head_to_pa(20))
    assert pumps.power(flow, 60, 1, [1, 0.001]) == pytest.approx(units.bhp_to_w(2))


def test_affinity_scaling_with_frequency_and_stages():
    """Head scales with stages and frequency squared, power with frequency cubed.

    At half the reference frequency, four stages give the head and eight stages the power of
    one stage at the reference frequency.
    """
    flow = units.bbl_per_day_to_m3s(500)
    head = pumps.head(flow, constants.ESP_REFERENCE_FREQUENCY, 1, [5, 0.02])
    power = pumps.power(flow, constants.ESP_REFERENCE_FREQUENCY, 1, [5, 0.02])
    assert pumps.head(flow, 30, 4, [5, 0.02]) == pytest.approx(head)
    assert pumps.power(flow, 30, 8, [5, 0.02]) == pytest.approx(power)
