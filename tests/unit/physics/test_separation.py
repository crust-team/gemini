"""Flow split, degasser, cyclone and dosing relations."""

import pytest

from gemini.physics import separation
from tests.fixtures.equivalence import assert_function_matches


def test_split_flow_by_hand_and_on_arrays():
    """A 30 % bleed of 10 kg/s leaves 7 kg/s and takes 3 kg/s."""
    assert separation.split_flow(10.0, 0.3) == pytest.approx((7.0, 3.0))
    assert_function_matches(separation.split_flow, [(10.0, 0.3), (-4.0, 0.0), (2.0, 1.0)])
