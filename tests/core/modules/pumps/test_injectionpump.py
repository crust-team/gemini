"""Explicit placeholder behavior for InjectionPump."""

import pytest

from gemini.core.base.stream import Stream
from gemini.core.modules.pumps import InjectionPump


def test_unmodelled_equipment():
    """Valid ports still report that equipment physics is not modelled."""
    c = InjectionPump({"no_stages": 10, "pump_type": "DEFAULT-PUMP"})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["suction"]}
    with pytest.raises(NotImplementedError, match="injectionpump is not modelled yet"):
        c({}, streams)
