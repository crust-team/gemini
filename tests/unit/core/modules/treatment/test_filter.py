"""Mass conservation for Filter."""

from gemini.core.modules.treatment import Filter
from gemini.core.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = Filter()
    result = c(inlet=Stream(m_dot=1, T=300, p=1e6))
    assert sum(s.m_dot for s in result.outlets.values() if isinstance(s, Stream)) == 1
    assert result.outlets["outlet"].T == 300
    assert result.outlets["outlet"].p >= 0


def test_clogging_alarm():
    """Measured pressure differential triggers the configured clogging alarm."""
    c = Filter()
    assert not c.health(None, {"pressure_drop": 40000}).alarm
    assert c.health(None, {"pressure_drop": 51000}).alarm
    assert c.health(None, {}) is None


def test_filter_matches_traced():
    """The quadratic loss traces and equals one call per row."""
    rows = [dict(inlet=Stream(m_dot=m_dot, T=300, p=1e6)) for m_dot in (0, 20, 44.2, 60)]
    assert_module_matches(Filter(), rows)
