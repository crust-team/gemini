"""Reservoir IPR and monitoring checks using example design data."""

from pathlib import Path

import pytest

from gemini.core.legacy import tables as mapping
from gemini.core.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.core.types.flows import Stream

DATA = Path(__file__).parents[5] / "examples/legacy/gemini_project_bridge/old_project"


def test_example_production_and_decline():
    """The example PI controls drawdown, and a 16% decline raises an alarm."""
    p = mapping.reservoir_params_from_gemini(
        mapping.read_property(DATA / "reservoir_c1b5.param"),
        mapping.read_property(DATA / "production_well_c774.param"),
    )
    c = ProductionReservoir().update_params(**p)
    result = c(production_rate=40)
    out, flow = result.outputs, 40 / 1068
    assert out.drawdown == pytest.approx(flow / c.productivity_index)
    pressure = out.bottomhole_pressure
    assert not c.health(result, dict(flow=flow, bottomhole_pressure=pressure)).alarm
    assert c.health(result, dict(flow=flow * 0.84, bottomhole_pressure=pressure)).alarm


def test_injection_zero_radius_is_explicit():
    """Unconfigured example drainage radius leaves only radial diagnostics unavailable."""
    p = mapping.reservoir_params_from_gemini(
        mapping.read_property(DATA / "reservoir_28fc.param"),
        mapping.read_property(DATA / "injection_well_a06b.param"),
        "injection",
    )
    c = InjectionReservoir().update_params(**p)
    result = c(sandface=Stream(m_dot=-40, T=300, p=23e6))
    out = result.outputs
    assert out.bottomhole_pressure > c.pressure
    assert out.radial_bottomhole_pressure is None
    assert not c.health(
        result, dict(flow=40 / 1068, bottomhole_pressure=out.bottomhole_pressure)
    ).alarm


def test_ipr_helpers_match_the_call_outputs():
    """``sandface_stream`` and ``required_pressure`` give the pressures a call reports."""
    common = dict(
        temperature=353.15,
        permeability=1e-12,
        thickness=100,
        drainage_radius=0,
        top_depth=2400,
        wellbore_radius=0.1,
    )
    producer = ProductionReservoir().update_params(
        pressure=250e5, productivity_index=10 / 3.6e8, **common
    )
    sandface = producer.sandface_stream(40)
    assert sandface.m_dot == 40 and sandface.T == 353.15
    assert sandface.p == producer(production_rate=40).outputs.bottomhole_pressure
    assert sandface.p == pytest.approx(250e5 - 40 / 1000 * 3.6e8 / 10)
    sink = InjectionReservoir().update_params(
        pressure=240e5, injectivity_index=10 / 3.6e8, **common
    )
    arriving = Stream(m_dot=-40, T=300, p=230e5)
    assert sink.required_pressure(arriving) == sink(sandface=arriving).outputs.bottomhole_pressure
    assert sink.required_pressure(arriving) == pytest.approx(240e5 + 40 / 1000 * 3.6e8 / 10)
