"""Explicit placeholder behavior for BoosterPump."""

import pytest

from gemini.components.pumps import BoosterPump
from gemini.core.base.stream import Stream


def test_unmodelled_equipment():
    """Valid ports still report that equipment physics is not modelled."""
    c = BoosterPump({})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["suction"]}
    with pytest.raises(NotImplementedError, match="boosterpump is not modelled yet"):
        c.compute({}, streams)
