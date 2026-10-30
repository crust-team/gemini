"""Energy conversion through an efficiency."""

from gemini.physics import energy
from tests.fixtures.equivalence import assert_function_matches


def test_input_power_is_the_useful_power_over_the_efficiency():
    """A 90 % converter draws 1000 W for 900 W."""
    assert energy.input_power(900.0, 0.9) == 1000
    assert_function_matches(energy.input_power, [(900.0, 0.9), (0.0, 0.8)])
