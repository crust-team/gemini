"""The annuity and the lifetime cost."""

import pytest

from gemini.evaluate._utils import cost


def test_annuity_is_the_discounted_year_count():
    """Ten years at 5 % are 7.7217 discounted years; at 0 % they are ten."""
    assert cost.annuity(0.05, 10) == pytest.approx(7.721734929, rel=1e-9)
    assert cost.annuity(0.0, 10) == 10.0
