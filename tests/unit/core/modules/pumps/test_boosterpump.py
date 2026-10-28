"""Mass conservation and fidelity for BoosterPump."""

from gemini.core.modules.pumps import BoosterPump
from gemini.core.types.flows import Stream


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = BoosterPump()
    result = c(suction=Stream(m_dot=1, T=300, p=1e6))
    assert sum(s.m_dot for s in result.outlets.values() if isinstance(s, Stream)) == 1
    assert result.outlets["discharge"].T == 300
    assert result.outlets["discharge"].p >= 0
    assert c.fidelity == "passthrough"
