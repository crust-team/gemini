"""Reservoir IPR and monitoring checks using example design data."""

from pathlib import Path

import pytest

from gemini.components.subsurface import InjectionReservoir, ProductionReservoir
from gemini.core.base.stream import Stream
from gemini.core.plant import param_mapping as mapping

DATA = Path(__file__).parents[3] / "datasets/geothermal_example"


def test_example_production_and_decline():
    """The example PI controls drawdown, and a 16% decline raises an alarm."""
    p = mapping.reservoir_params_from_gemini(
        mapping.read_property(DATA / "reservoir_c1b5.param"),
        mapping.read_property(DATA / "production_well_c774.param"),
    )
    c = ProductionReservoir(p)
    out, _ = c.compute({"m_dot": 40}, {})
    flow = 40 / 1068
    assert out.drawdown == pytest.approx(flow / c.params.productivity_index)
    assert not c.health(out, dict(flow=flow, bottomhole_pressure=out.bottomhole_pressure)).alarm
    assert c.health(out, dict(flow=flow * 0.84, bottomhole_pressure=out.bottomhole_pressure)).alarm


def test_injection_zero_radius_is_explicit():
    """Unconfigured example drainage radius leaves only radial diagnostics unavailable."""
    p = mapping.reservoir_params_from_gemini(
        mapping.read_property(DATA / "reservoir_28fc.param"),
        mapping.read_property(DATA / "injection_well_a06b.param"),
        "injection",
    )
    c = InjectionReservoir(p)
    out, _ = c.compute({}, {"sandface": Stream(m_dot=-40, T=300, p=23e6)})
    assert out.bottomhole_pressure > c.params.pressure
    assert out.radial_bottomhole_pressure is None
    assert not c.health(
        out, dict(flow=40 / 1068, bottomhole_pressure=out.bottomhole_pressure)
    ).alarm
