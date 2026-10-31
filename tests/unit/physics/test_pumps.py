"""TNO pump polynomials on the historical US basis."""

import pytest

from gemini.physics import pumps


def test_centrifugal_curve_and_parabolic_efficiency():
    """At half speed the head curve drops to c0/4 at zero flow; efficiency peaks at the bep."""
    assert pumps.centrifugal_head(0.0, 0.5, [100.0, 0.0, -1.0]) == pytest.approx(25)
    assert pumps.centrifugal_head(2.0, 1.0, [100.0, -3.0, -1.0]) == pytest.approx(90)
    load = pumps.best_efficiency_ratio(0.03, 0.5, 0.06)
    assert load == pytest.approx(1)
    assert pumps.parabolic_efficiency(0.8, load) == pytest.approx(0.8)
    assert pumps.parabolic_efficiency(0.8, 0.5) == pytest.approx(0.6)
