"""Explicit placeholder behavior for Filter."""

import pytest

from gemini.core.base.stream import Stream
from gemini.core.modules.treatment import Filter


def test_unmodelled_equipment():
    """Valid ports still report that equipment physics is not modelled."""
    c = Filter({})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["inlet"]}
    with pytest.raises(NotImplementedError, match="filter is not modelled yet"):
        c({}, streams)


def test_clogging_alarm():
    """Measured pressure differential triggers the configured clogging alarm."""
    c = Filter({})
    assert not c.health(None, {"pressure_drop": 40000}).alarm
    assert c.health(None, {"pressure_drop": 51000}).alarm
    assert c.health(None, {}) is None
