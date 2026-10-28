"""Mass conservation and fidelity for InjectionPump."""

from gemini.core.modules.pumps import InjectionPump
from gemini.core.types.flows import Stream


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = InjectionPump({"no_stages": 10, "pump_type": "DEFAULT-PUMP"})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["suction"]}
    result = c({"discharge_pressure": 2e6}, streams)
    assert sum(s.m_dot for s in result.streams.values()) == 1
    assert result.streams["discharge"].T == 300
    assert result.streams["discharge"].p >= 0
    assert c.schema()["fidelity"] in {"simple", "passthrough"}
