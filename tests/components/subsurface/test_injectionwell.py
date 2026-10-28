"""Injection well sign convention and mass conservation."""

from pathlib import Path

from gemini.components.subsurface import InjectionWell
from gemini.core.base.stream import Stream
from gemini.core.plant import param_mapping as mapping


def test_injection_flow_sign_and_pressure():
    """A positive surface rate becomes the documented negative downhole stream rate."""
    data = Path(__file__).parents[3] / "datasets/geothermal_example"
    c = InjectionWell(
        mapping.injectionwell_params_from_gemini(
            mapping.read_property(data / "injection_well_a06b.param")
        )
    )
    out, streams = c.compute({}, {"wellhead": Stream(m_dot=40, T=300, p=5e6)})
    assert out.dp_friction < 0 and out.dp_gravity > 0
    assert streams["bottom"].m_dot == -40
    assert out.bottomhole_pressure > 5e6
