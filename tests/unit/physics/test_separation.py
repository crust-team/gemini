"""Flow split, degasser, cyclone and dosing relations."""

import pytest

from gemini.physics import separation
from tests.fixtures.equivalence import assert_function_matches


def test_split_flow_by_hand_and_on_arrays():
    """A 30 % bleed of 10 kg/s leaves 7 kg/s and takes 3 kg/s."""
    assert separation.split_flow(10.0, 0.3) == pytest.approx((7.0, 3.0))
    assert_function_matches(separation.split_flow, [(10.0, 0.3), (-4.0, 0.0), (2.0, 1.0)])


def test_degasser_split_conserves_the_free_gas():
    """Half the gas of a 2 % stream leaves; the liquid keeps 1 % of the free gas by mass."""
    liquid, gas, remaining = separation.degasser_split(10.0, 0.02, 0.5)
    assert gas == pytest.approx(0.1)
    assert liquid == pytest.approx(9.9)
    assert remaining * liquid == pytest.approx(0.1)
    rows = [(10.0, 0.02, 0.5), (5.0, 0.0, 0.9), (3.0, 0.1, 0.0), (3.0, 0.1, 1.0)]
    assert_function_matches(separation.degasser_split, rows)


def test_cyclone_sand_by_hand_and_on_arrays():
    """Removing 80 % of 0.01 kg/m3 sand at 0.05 m3/s takes 4e-4 kg/s and leaves 0.002 kg/m3."""
    rate, residual = separation.cyclone_sand(0.8, 0.01, 0.05)
    assert rate == pytest.approx(4e-4)
    assert residual == pytest.approx(0.002)
    assert_function_matches(separation.cyclone_sand, [(0.8, 0.01, 0.05), (0.0, 0.02, 0.1)])


def test_dosing_flows_by_hand_and_on_arrays():
    """10 ppm of a 30 % active product in 100 kg/s is 1e-3 kg/s product and 3e-4 kg/s active."""
    product, active = separation.dosing_flows(1e-5, 100.0, 0.3)
    assert product == pytest.approx(1e-3)
    assert active == pytest.approx(3e-4)
    assert_function_matches(separation.dosing_flows, [(1e-5, 100.0, 0.3), (0.0, 50.0, 0.5)])


def test_filter_defaults_keep_their_values():
    """The design flow is 149 m3/h of 1068 kg/m3 brine."""
    assert separation.FILTER_NOMINAL_MASS_FLOW == 149 / 3600 * 1068
