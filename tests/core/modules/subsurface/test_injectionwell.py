"""Injection well sign convention and mass conservation."""

from pathlib import Path

from gemini.core.base.stream import Stream
from gemini.core.modules.subsurface import InjectionWell
from gemini.core.plant import param_mapping as mapping


def test_injection_flow_sign_and_pressure():
    """A positive surface rate becomes the documented negative downhole stream rate."""
    data = Path(__file__).parents[4] / "datasets/geothermal_doublet"
    c = InjectionWell(
        mapping.injectionwell_params_from_gemini(
            mapping.read_property(data / "injection_well_a06b.param")
        )
    )
    out, streams = c({}, {"wellhead": Stream(m_dot=40, T=300, p=5e6)})
    assert out.dp_friction < 0 and out.dp_gravity > 0
    assert streams["bottom"].m_dot == -40
    assert out.bottomhole_pressure > 5e6


def test_corrosion_profile_uses_injection_flow_sign():
    """Positive surface flow and negative downhole flow describe the same injection state."""
    data = Path(__file__).parents[4] / "datasets/geothermal_doublet"
    well = InjectionWell(
        mapping.injectionwell_params_from_gemini(
            mapping.read_property(data / "injection_well_a06b.param")
        )
    )
    stream = Stream(m_dot=40, T=300, p=5e6)
    chemistry = {"co2_fraction": 0.1}
    assert well.corrosion_profile(stream, chemistry, "DLM") == well.corrosion_profile(
        stream.with_(m_dot=-40), chemistry, "DLM"
    )
