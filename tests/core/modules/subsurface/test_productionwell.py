"""Production well traversal and ESP splitting across a trajectory section."""

from pathlib import Path

import pytest

from gemini.core.base.stream import Stream
from gemini.core.config import param_mapping as mapping
from gemini.core.modules.subsurface import ProductionWell


def test_split_esp_traversal():
    """Split at 600 m inside a section; pumping raises the resulting wellhead pressure."""
    data = Path(__file__).parents[4] / "datasets/geothermal_doublet"
    c = ProductionWell(
        mapping.productionwell_params_from_gemini(
            mapping.read_property(data / "production_well_c774.param"),
            esp_property=mapping.read_property(data / "esp_1ee3.param"),
        )
    )
    stream = Stream(m_dot=40, T=353.15, p=25e6)
    intake = c.intake_conditions(stream)
    out = c.wellhead_from_discharge(intake.with_(p=intake.p + 3e6))
    passive = c.wellhead_from_discharge(intake)
    assert out.p - passive.p == pytest.approx(3e6)
    assert out.m_dot == stream.m_dot
    assert len(c.corrosion_profile(stream, {"co2_fraction": 0.1}, model="DLM")) == len(
        c.params.path.sections
    )
    assert len(c.erosion_check(stream)["velocity"]) == len(c.params.path.sections)
