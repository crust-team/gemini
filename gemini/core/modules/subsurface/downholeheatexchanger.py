"""Deep closed-loop downhole heat exchanger in a linear geothermal gradient."""

import math

from gemini.core.modules.module import Module
from gemini.core.physics import ground
from gemini.core.types import (
    Duration,
    Inlet,
    Length,
    LinearThermalResistance,
    Outlet,
    Output,
    Parameter,
    Power,
    Stream,
    Temperature,
    TemperatureGradient,
    ThermalConductivity,
    ThermalDiffusivity,
)
from gemini.errors import ConfigurationError, PhysicsRangeError


class DownholeHeatExchanger(Module):
    """Deep coaxial closed-loop heat exchanger with Ramey's quasi-steady rock resistance.

    The circuit fluid flows down the annulus to ``depth``, exchanging heat with rock whose
    undisturbed temperature rises linearly from ``surface_temperature`` with
    ``geothermal_gradient``, and returns through an insulated centre pipe. Per unit length the
    fluid sees the resistance R = R_b + f(t) / (2 pi k): the ``borehole_resistance`` R_b
    (fluid to borehole wall) plus the transient rock resistance with Ramey's time function
    f(t) = ln(2 sqrt(alpha t) / r_b) - gamma / 2 evaluated at the quasi-steady
    ``operating_time`` t (Ramey 1962, Wellbore heat transmission, J. Petroleum Technology
    14(4), 427-435; ``ground.ramey_time_function``). The steady energy balance
    m_dot cp dT/dz = (T_rock(z) - T) / R gives Ramey's exact profile with the relaxation
    length A = m_dot cp R (``ground.ramey_fluid_temperature``), and the fluid leaves at the
    bottom-hole temperature: outlet_T = T(depth). ``heat_extraction_rate`` is
    m_dot cp (outlet_T - T_in); heat taken from the rock is ``heat_absorbed`` and heat given to
    it (an inlet warmer than the rock) ``heat_loss``, so the stream audit closes.

    Assumptions: steady state at a fixed operating time (no load history; the rock
    resistance applies a constant, uniform heat flux along the depth); a perfectly insulated
    return pipe, so no heat exchange between the up- and down-flowing fluid (a U-tube or a
    poorly insulated coaxial pipe delivers less); constant fluid and rock properties; no
    friction heating or pressure work; mass and pressure pass unchanged (hydraulics belong to
    a pipe or well module). Valid for alpha t / r_b**2 >= 25 (``ground.MIN_RAMEY_FOURIER``),
    typically after a few days of operation. Zero flow exchanges no heat and returns the
    inlet unchanged.
    """

    def __init__(self):
        """Declare the well geometry, the geothermal profile and the rock properties."""
        super().__init__()

        # Parameters
        self.depth = Parameter(Length, gt=0)
        self.surface_temperature = Parameter(Temperature)
        self.geothermal_gradient = Parameter(TemperatureGradient)
        self.rock_conductivity = Parameter(ThermalConductivity, calibratable=True)
        self.rock_diffusivity = Parameter(ThermalDiffusivity)
        self.borehole_radius = Parameter(Length, gt=0)
        self.borehole_resistance = Parameter(LinearThermalResistance, calibratable=True)
        self.operating_time = Parameter(Duration, gt=0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.heat_extraction_rate = Output(Power)
        self.outlet_T = Output(Temperature)
        self.heat_absorbed = Output(Power)
        self.heat_loss = Output(Power)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Return the fluid at the temperature it reaches at the bottom of the annulus."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet.with_(T=self._outlet_temperature(inlet))

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        outlet = outlets.outlet
        rate = inlet.m_dot * inlet.fluid.properties(inlet.p, inlet.T).cp_l * (outlet.T - inlet.T)
        self.heat_extraction_rate = rate
        self.outlet_T = outlet.T
        self.heat_absorbed = max(rate, 0)
        self.heat_loss = max(-rate, 0)

    def _outlet_temperature(self, inlet):
        """Return the bottom-hole fluid temperature [K] from Ramey's profile."""
        if inlet.m_dot < 0:
            raise PhysicsRangeError(f"{self.path}: inlet.m_dot = {inlet.m_dot} kg/s; expected >= 0")
        if inlet.m_dot == 0:
            return inlet.T
        capacity_rate = inlet.m_dot * inlet.fluid.properties(inlet.p, inlet.T).cp_l
        relaxation = capacity_rate * (self.borehole_resistance + self._rock_resistance())
        return ground.ramey_fluid_temperature(
            inlet.T, self.surface_temperature, self.geothermal_gradient, self.depth, relaxation
        )

    def _rock_resistance(self):
        """Return the transient rock resistance f(t) / (2 pi k) [m K/W]."""
        try:
            function = ground.ramey_time_function(
                self.operating_time, self.rock_diffusivity, self.borehole_radius
            )
        except PhysicsRangeError as error:
            raise ConfigurationError(f"{self.path}: operating_time rejected: {error}") from error
        return function / (2 * math.pi * self.rock_conductivity)
