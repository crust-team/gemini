"""Injection well sign convention and mass conservation."""

from pathlib import Path

from gemini.core.legacy import tables as mapping
from gemini.core.modules.subsurface import InjectionWell
from gemini.core.types.flows import Stream


def test_injection_flow_sign_and_pressure():
    """Ports conserve mass while the internal DPDT correlation retains its negative sign."""
    data = Path(__file__).parents[5] / "examples/legacy/gemini_project_bridge/old_project"
    c = InjectionWell(
        **mapping.injectionwell_params_from_gemini(
            mapping.read_property(data / "injection_well_a06b.param")
        )
    )
    result = c(wellhead=Stream(m_dot=40, T=300, p=5e6))
    out, streams = result.outputs, result.outlets
    assert out.dp_friction < 0 and out.dp_gravity > 0
    assert streams["bottom"].m_dot == 40
    assert out.bottomhole_pressure > 5e6


def test_corrosion_profile_uses_injection_flow_sign():
    """Positive surface flow and negative downhole flow describe the same injection state."""
    data = Path(__file__).parents[5] / "examples/legacy/gemini_project_bridge/old_project"
    well = InjectionWell(
        **mapping.injectionwell_params_from_gemini(
            mapping.read_property(data / "injection_well_a06b.param")
        )
    )
    stream = Stream(m_dot=40, T=300, p=5e6)
    chemistry = {"co2_fraction": 0.1}
    assert well.corrosion_profile(stream, chemistry, "DLM") == well.corrosion_profile(
        stream.with_(m_dot=-40), chemistry, "DLM"
    )
