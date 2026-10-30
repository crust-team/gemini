"""Closed-loop borehole field: effectiveness, lumped ground state and balances."""

import math

import pytest

import gemini as gm
from gemini import ops
from gemini.modules import Module, energy_balance, mass_balance
from gemini.modules.heating import ElectricBoiler
from gemini.modules.subsurface import BoreholeField
from gemini.types import Inlet, Outlet, Output, Stream
from tests.fixtures.equivalence import assert_function_matches, assert_same_error
from tests.fixtures.errors import raises

BRINE = Stream(m_dot=3, T=273.15, p=3e5)
CP = 4217.4
DAY = 86400.0


def field():
    """Return a ten-borehole field of 150 m at 6 m spacing."""
    return BoreholeField().update_params(
        borehole_count=10,
        borehole_depth=150,
        borehole_radius=0.075,
        borehole_spacing=6,
        borehole_resistance=0.1,
        ground_conductivity=2.0,
        ground_volumetric_heat_capacity=2.2e6,
        undisturbed_ground_temperature=283.15,
    )


def hand_effectiveness(m_dot):
    """Return the hand-computed loop effectiveness [-] at a mass flow [kg/s]."""
    r_e, r_b = 6 / math.sqrt(math.pi), 0.075
    x = (r_b / r_e) ** 2
    cell = (math.log(r_e / r_b) / (1 - x) ** 2 - 1 / (2 * (1 - x)) - 0.25) / (2 * math.pi * 2.0)
    return 1 - math.exp(-1500 / (0.1 + cell) / (m_dot * CP))


def surroundings():
    """Return the hand-computed field-to-surroundings conductance [W/K]."""
    diameter = 2 * math.sqrt(360 / math.pi)
    return 2.0 * 2 * math.pi * 150 / math.log(4 * 150 / diameter)


class HeatPumpLoop(Module):
    """Ground loop followed by a heater standing in for the heat pump evaporator return."""

    def __init__(self):
        """Declare the test composite."""
        super().__init__()

        # Modules
        self.field = field()
        self.heater = ElectricBoiler().update_params(capacity=1e5, efficiency=0.9)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.heat_extraction_rate = Output.of(self.field.heat_extraction_rate)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Pass the brine through the field and the heater."""

        # Modules
        ground = self.field(inlet=inlets.inlet)
        heated = self.heater(inlet=ground.outlets.outlet, temperature_setpoint=280)

        # Outlets
        outlet = heated.outlets.outlet

        outlets = dict(outlet=outlet)
        return outlets


def test_plain_call_extracts_with_the_loop_effectiveness():
    """At the undisturbed ground temperature Q = eps m_dot cp (T_u - T_in)."""
    module = field()
    result = module(inlet=BRINE)
    out = result.outputs
    rate = hand_effectiveness(3) * 3 * CP * 10
    assert module.initial_state() == {"ground_temperature_change": 0}
    assert out.heat_extraction_rate == pytest.approx(rate, rel=1e-12)
    assert out.outlet_T == pytest.approx(273.15 + rate / (3 * CP))
    assert out.fluid_mean_temperature == pytest.approx((273.15 + out.outlet_T) / 2)
    assert out.ground_temperature == 283.15 and out.heat_absorbed == out.heat_extraction_rate
    assert out.heat_loss == 0
    assert energy_balance(module, result)["relative_residual"] < 1e-12
    assert mass_balance(module, result)["residual"] == 0


def test_two_steps_follow_the_exact_ground_response():
    """Each step solves the linear ground balance exactly for a constant inlet."""
    module = field()
    state, _ = module.step(None, 30 * DAY, {"inlet": BRINE})
    exchange = hand_effectiveness(3) * 3 * CP
    total = exchange + surroundings()
    equilibrium = exchange * (273.15 - 283.15) / total
    decay = math.exp(-total * 30 * DAY / (2.2e6 * 360 * 150))
    assert state["ground_temperature_change"] == pytest.approx(equilibrium * (1 - decay))
    state, result = module.step(state, 30 * DAY, {"inlet": BRINE})
    assert result.outputs.ground_temperature == pytest.approx(283.15 + equilibrium * (1 - decay))
    double, _ = module.step(None, 60 * DAY, {"inlet": BRINE})
    assert state["ground_temperature_change"] == pytest.approx(
        double["ground_temperature_change"], rel=1e-12
    )


def test_heat_rejection_recovery_and_zero_flow():
    """Warm inlets reject heat as heat_loss; without flow the ground recovers on its own."""
    module = field()
    result = module(inlet=BRINE.with_(T=303.15))
    assert result.outputs.heat_extraction_rate < 0 and result.outputs.heat_absorbed == 0
    assert result.outputs.heat_loss == -result.outputs.heat_extraction_rate
    assert energy_balance(module, result)["relative_residual"] < 1e-12
    still = BRINE.with_(m_dot=0)
    state, result = module.step({"ground_temperature_change": -2.0}, 365 * DAY, {"inlet": still})
    decay = math.exp(-surroundings() * 365 * DAY / (2.2e6 * 360 * 150))
    assert state["ground_temperature_change"] == pytest.approx(-2.0 * decay)
    assert result.outlets.outlet.T == still.T and result.outputs.heat_extraction_rate == 0


def test_invalid_flow_and_geometry():
    """Reverse flow and geometries outside the cell and shape-factor ranges are rejected."""
    with pytest.raises(gm.errors.PhysicsError, match="inlet.m_dot = -1"):
        field()(inlet=BRINE.with_(m_dot=-1))
    with raises(gm.errors.ValidationError, "invalid_design", match="field geometry rejected"):
        field().update_params(borehole_spacing=0.1)(inlet=BRINE)
    shallow = field().update_params(borehole_count=400, borehole_depth=10)
    with raises(gm.errors.ValidationError, "invalid_design", match="expected ln"):
        shallow.step(None, DAY, {"inlet": BRINE})


def test_composite_step_advances_the_ground():
    """A composite steps the field through its forward."""
    loop = HeatPumpLoop()
    state, _ = loop.step(None, 7 * DAY, {"inlet": BRINE})
    state, result = loop.step(state, 7 * DAY, {"inlet": BRINE})
    assert state["field"]["ground_temperature_change"] < 0
    assert 0 < result.outputs.heat_extraction_rate < hand_effectiveness(3) * 3 * CP * 10


def test_field_arithmetic_matches_on_arrays():
    """The loop conductance, surroundings and ground heat capacity agree on arrays."""
    module = field()

    @ops.physics
    def numbers(m_dot, T, p):
        inlet = Stream(m_dot=m_dot, T=T, p=p)
        return dict(
            exchange=module._effective_conductance(inlet),
            surroundings=module._surroundings_conductance(),
            capacity=module._ground_heat_capacity(),
        )

    rows = [(3.0, 273.15, 3e5), (0.0, 273.15, 3e5), (0.05, 300.0, 3e5)]
    assert_function_matches(numbers, rows)
    assert_same_error(numbers, rows + [(-1.0, 273.15, 3e5)], gm.errors.PhysicsError)


def test_zero_flow_does_not_evaluate_the_cell_geometry():
    """A cell no wider than the borehole is bad design data only where the loop flows."""
    module = field().update_params(borehole_spacing=0.1)
    conductance = ops.physics(module._effective_conductance)
    assert conductance(BRINE.with_(m_dot=0)) == 0
    with raises(gm.errors.ValidationError, "invalid_design", match="field geometry rejected"):
        conductance(BRINE)
