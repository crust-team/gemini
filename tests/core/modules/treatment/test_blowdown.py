"""Mass conservation and fidelity for Blowdown."""

from gemini.core.modules.treatment import Blowdown
from gemini.core.types.flows import Stream


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = Blowdown({})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["inlet"]}
    result = c({}, streams)
    assert sum(s.m_dot for s in result.streams.values()) == 1
    assert result.streams["outlet"].T == 300
    assert result.streams["outlet"].p >= 0
    assert c.schema()["fidelity"] in {"simple", "passthrough"}
