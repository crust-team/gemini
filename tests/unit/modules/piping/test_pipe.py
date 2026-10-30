"""Pipe friction regimes, static head, ambient heat exchange, balances and limits."""

import math

import pytest

import gemini as gm
from gemini.modules import energy_balance, mass_balance
from gemini.modules.piping import Pipe
from gemini.types import Fluid, Stream
from tests.fixtures.equivalence import assert_module_matches
from tests.fixtures.errors import raises

STREAM = Stream(m_dot=10, T=353.15, p=5e5)


def pipe(**changes):
    """Return a 1 km DN100 steel pipe rising 5 m with a weakly insulated wall."""
    params = dict(
        length=1000, inner_diameter=0.1, elevation_change=5, heat_transfer_coefficient=1.0
    )
    return Pipe().update_params(**(params | changes))


def test_turbulent_flow_matches_hand_calculation():
    """Swamee–Jain friction, static head and the exponential cooling profile, by hand."""
    result = pipe()(inlet=STREAM, ambient_temperature=283.15)
    velocity = 10 / 1000 / (math.pi * 0.1**2 / 4)
    reynolds = velocity * 1000 * 0.1 / 0.001
    friction_factor = 0.25 / math.log10(4.5e-5 / (3.7 * 0.1) + 5.74 / reynolds**0.9) ** 2
    friction = friction_factor * 1000 / 0.1 * 1000 * velocity**2 / 2
    outlet_T = 283.15 + 70 * math.exp(-1.0 * math.pi * 0.1 * 1000 / (10 * 4217.4))
    out = result.outputs
    assert out.velocity == pytest.approx(velocity, rel=1e-14)
    assert out.pressure_drop == pytest.approx(friction + 1000 * 9.81 * 5, rel=1e-12)
    assert out.outlet_T == pytest.approx(outlet_T, rel=1e-14)
    assert out.heat_loss == pytest.approx(10 * 4217.4 * (353.15 - outlet_T), rel=1e-9)
    assert out.heat_absorbed == 0
    assert result.outlets.outlet.m_dot == 10
    assert energy_balance(pipe(), result)["relative_residual"] < 1e-12
    assert mass_balance(pipe(), result)["residual"] == 0


def test_laminar_flow_and_continuous_transition():
    """Laminar flow follows Hagen–Poiseuille and the transition bridge has no jumps."""
    module = pipe(elevation_change=0, heat_transfer_coefficient=0)
    laminar = module(inlet=STREAM.with_(m_dot=0.1), ambient_temperature=283.15).outputs
    velocity = 0.1 / 1000 / (math.pi * 0.1**2 / 4)
    assert laminar.pressure_drop == pytest.approx(32 * 0.001 * 1000 * velocity / 0.1**2)
    for reynolds in (2300, 4000):
        m_dot = reynolds * 0.001 / 0.1 * math.pi * 0.1**2 / 4
        below, above = (
            module(
                inlet=STREAM.with_(m_dot=m_dot * factor), ambient_temperature=283.15
            ).outputs.pressure_drop
            for factor in (1 - 1e-9, 1 + 1e-9)
        )
        assert above == pytest.approx(below, rel=1e-6)
    drops = [
        module(inlet=STREAM.with_(m_dot=m_dot), ambient_temperature=283.15).outputs.pressure_drop
        for m_dot in (0.15, 0.2, 0.25, 0.3, 0.35)
    ]
    assert drops == sorted(drops)


def test_cold_fluid_absorbs_heat_and_long_pipes_approach_ambient():
    """Chilled water gains heat, and a huge exchange area never overshoots the ambient."""
    chilled = pipe()(inlet=STREAM.with_(T=280.15), ambient_temperature=300.15)
    assert chilled.outputs.heat_loss == 0 and chilled.outputs.heat_absorbed > 0
    assert 280.15 < chilled.outputs.outlet_T < 300.15
    assert energy_balance(pipe(), chilled)["relative_residual"] < 1e-12
    bare = pipe(heat_transfer_coefficient=1e4)(
        inlet=STREAM.with_(m_dot=0.5), ambient_temperature=283.15
    )
    assert bare.outputs.outlet_T == pytest.approx(283.15) and bare.outputs.outlet_T >= 283.15
    adiabatic = pipe(heat_transfer_coefficient=0)(inlet=STREAM, ambient_temperature=283.15)
    assert adiabatic.outputs.outlet_T == STREAM.T and adiabatic.outputs.heat_loss == 0


def test_zero_flow_keeps_only_the_static_head():
    """A stopped pipe has no friction or heat exchange; a descending one gains pressure."""
    module = pipe(elevation_change="-10 ft")
    result = module(inlet=STREAM.with_(m_dot=0), ambient_temperature=283.15)
    assert result.outputs.pressure_drop == pytest.approx(-1000 * 9.81 * 3.048)
    assert result.outputs.velocity == 0 and result.outputs.outlet_T == STREAM.T
    assert result.outputs.heat_loss == result.outputs.heat_absorbed == 0
    assert energy_balance(module, result)["residual"] == 0


def test_invalid_inputs_raise():
    """Reverse flow, free gas, impossible rise and a negative outlet pressure are rejected."""
    with pytest.raises(gm.errors.PhysicsError, match="inlet.m_dot = -1"):
        pipe()(inlet=STREAM.with_(m_dot=-1), ambient_temperature=283.15)
    gassy = STREAM.with_(fluid=Fluid(gas_mass_fraction=0.01))
    with pytest.raises(gm.errors.PhysicsError, match="gas_mass_fraction"):
        pipe()(inlet=gassy, ambient_temperature=283.15)
    with raises(gm.errors.ValidationError, "invalid_design", match="pipe: elevation_change = 2000"):
        pipe(elevation_change=2000)(inlet=STREAM, ambient_temperature=283.15)
    with pytest.raises(gm.errors.PhysicsError, match="outlet pressure"):
        pipe()(inlet=STREAM.with_(m_dot=40), ambient_temperature=283.15)
    with raises(gm.errors.ValidationError, "missing_value"):
        pipe()(inlet=STREAM)
    with pytest.raises(gm.errors.ValidationError):
        pipe(inner_diameter=0)


def test_pipe_matches_traced_across_regimes():
    """Laminar, transition, turbulent, stopped and heat-absorbing rows equal one call per row."""
    rows = [
        dict(inlet=Stream(m_dot=m_dot, T=T, p=5e5), ambient_temperature=ambient)
        for m_dot, T, ambient in [
            (0.05, 353.15, 283.15),
            (0.08, 353.15, 283.15),
            (10, 353.15, 283.15),
            (0, 353.15, 283.15),
            (10, 283.15, 320.0),
        ]
    ]
    assert_module_matches(pipe(), rows)
