"""Mass conservation and fidelity for Filter."""

from gemini.core.modules.treatment import Filter
from gemini.core.types.flows import Stream


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = Filter({})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["inlet"]}
    result = c({}, streams)
    assert sum(s.m_dot for s in result.streams.values()) == 1
    assert result.streams["outlet"].T == 300
    assert result.streams["outlet"].p >= 0
    assert c.schema()["fidelity"] in {"simple", "passthrough"}


def test_clogging_alarm():
    """Measured pressure differential triggers the configured clogging alarm."""
    c = Filter({})
    assert not c.health(None, {"pressure_drop": 40000}).alarm
    assert c.health(None, {"pressure_drop": 51000}).alarm
    assert c.health(None, {}) is None
