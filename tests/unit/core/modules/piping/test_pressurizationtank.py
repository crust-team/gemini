"""Pressure re-anchoring of a closed circuit, alone and inside a small piping network."""

import pytest

import gemini as gm
from gemini.core.modules import Module, energy_balance, mass_balance
from gemini.core.modules.piping import Mixer, Pipe, PressurizationTank, Splitter, Valve
from gemini.core.types import Boundary, Inlet, Outlet, Output, Stream, Temperature

RETURN = Stream(m_dot=10, T=323.15, p=1.2e5)


class Network(Module):
    """Two parallel branches, a pipe and a valve, joined and re-pressurised."""

    def __init__(self):
        """Declare the test network."""
        super().__init__()

        # Modules
        self.splitter = Splitter()
        self.pipe = Pipe().update_params(
            length=200, inner_diameter=0.08, elevation_change=0, u_value=2.0
        )
        self.valve = Valve().update_params(flow_coefficient="40 m3/h/bar^0.5")
        self.mixer = Mixer()
        self.tank = PressurizationTank()

        # Inlets
        self.inlet = Inlet(Stream)

        # Boundaries
        self.ambient_temperature = Boundary(Temperature)

        # Outputs
        self.heat_loss = Output.total("heat_loss")
        self.pressure_correction = Output.of("tank.pressure_correction")

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Split, pass both branches, mix and hold the circuit pressure."""

        # Modules
        split = self.splitter(feed_in=inlets.inlet, split_fraction=0.4)
        piped = self.pipe(
            inlet=split.outlets.first_out, ambient_temperature=self.ambient_temperature
        )
        throttled = self.valve(inlet=split.outlets.second_out, opening=0.8)
        mixed = self.mixer(first_in=piped.outlets.outlet, second_in=throttled.outlets.outlet)
        held = self.tank(inlet=mixed.outlets.mixed_out, pressure_setpoint="3 bar")

        # Outlets
        outlet = held.outlets.outlet

        outlets = dict(outlet=outlet)
        return outlets


def test_outlet_leaves_at_the_setpoint():
    """The tank sets the pressure and reports the correction; flow and temperature pass."""
    result = PressurizationTank()(inlet=RETURN, pressure_setpoint="2 bar")
    outlet = result.outlets.outlet
    assert outlet.p == 2e5 and (outlet.m_dot, outlet.T) == (10, 323.15)
    assert result.outputs.pressure_correction == pytest.approx(0.8e5)
    relieved = PressurizationTank()(inlet=RETURN, pressure_setpoint="1 bar").outputs
    assert relieved.pressure_correction == pytest.approx(-0.2e5)
    reverse = PressurizationTank()(inlet=RETURN.with_(m_dot=-1), pressure_setpoint=2e5)
    assert reverse.outlets.outlet.m_dot == -1
    assert energy_balance(PressurizationTank(), result)["residual"] == 0
    assert mass_balance(PressurizationTank(), result)["residual"] == 0


def test_invalid_setpoint_and_missing_command_raise():
    """A zero or missing pressure setpoint is rejected."""
    with pytest.raises(gm.errors.DeclarationError):
        PressurizationTank()(inlet=RETURN, pressure_setpoint=0)
    with pytest.raises(gm.errors.MissingValueError):
        PressurizationTank()(inlet=RETURN)


def test_piping_network_closes_mass_and_energy():
    """A split, pipe, valve, mixer and tank network conserves mass and sensible energy."""
    network = Network()
    result = network(inlet=RETURN.with_(p=4e5), ambient_temperature=283.15)
    outlet = result.outlets.outlet
    assert outlet.m_dot == pytest.approx(10, rel=1e-15) and outlet.p == 3e5
    assert outlet.T < RETURN.T and result.outputs.heat_loss > 0
    pipe_out = result.children["pipe"].outlets.outlet.p
    valve_out = result.children["valve"].outlets.outlet.p
    assert result.children["mixer"].outputs.pressure_imbalance == pytest.approx(
        abs(pipe_out - valve_out)
    )
    assert result.outputs.pressure_correction == pytest.approx(3e5 - min(pipe_out, valve_out))
    assert energy_balance(network, result)["relative_residual"] < 1e-12
    assert mass_balance(network, result)["relative_residual"] < 1e-15
