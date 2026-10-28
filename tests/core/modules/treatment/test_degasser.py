"""Mass conservation and fidelity for Degasser."""

from gemini.core.modules.treatment import Degasser
from gemini.core.types.flows import Stream


def test_equipment_forward():
    """Equipment preserves mass and valid pressure/temperature."""
    c = Degasser({"heat_transfer_coeff": 100000})
    streams = {p: Stream(m_dot=1, T=300, p=1e6) for p in ["inlet"]}
    result = c({}, streams)
    assert sum(s.m_dot for s in result.streams.values() if isinstance(s, Stream)) == 1
    assert result.streams["liquid"].T == 300
    assert result.streams["liquid"].p >= 0
    assert c.schema()["fidelity"] in {"simple", "passthrough"}
