"""Surface pipeline with wall friction, elevation change and heat exchange with its surroundings."""

import math

from gemini.core.modules.module import Module
from gemini.core.physics import geometry, heat_transfer, hydraulics
from gemini.core.types import (
    Boundary,
    Elevation,
    HeatTransferCoefficient,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Power,
    PressureDifference,
    Speed,
    Stream,
    Temperature,
)
from gemini.errors import ConfigurationError, PhysicsRangeError

LAMINAR_REYNOLDS = 2300
"""Reynolds number [-] up to which pipe flow is taken as laminar (Hagen–Poiseuille)."""

TURBULENT_REYNOLDS = 4000
"""Reynolds number [-] from which pipe flow is taken as turbulent (Swamee–Jain)."""

COMMERCIAL_STEEL_ROUGHNESS = 4.5e-5
"""Absolute roughness [m] of new commercial steel pipe (Moody 1944, Friction factors for pipe
flow, Trans. ASME 66; the 0.045 mm of the Moody chart and Crane TP-410)."""


class Pipe(Module):
    """Surface pipeline carrying a single-phase liquid, with friction, elevation and heat loss.

    Pressure: ``p_out = p_in - dp_friction - rho g dz`` with ``dz`` the signed
    ``elevation_change`` from inlet to outlet (positive when the outlet is higher). The
    friction drop is Darcy–Weisbach ``f L/D rho v^2/2``: laminar ``f = 64/Re`` (Hagen–Poiseuille)
    up to Re = 2300, Swamee and Jain (1976, Explicit equations for pipe-flow problems, J. Hydraul.
    Div. ASCE 102) through ``hydraulics.darcy_weisbach_dp`` from Re = 4000, and in between a
    linear interpolation in Re of the friction drop at the two limits, a continuous bridge
    without physical claim for the intermittent transition regime.

    Heat: the fluid exchanges heat with surroundings at the fixed ``ambient_temperature``
    through the overall coefficient ``u_value`` referred to the inner wall area ``pi d L`` (the
    convention of the well path model). With constant ``u_value`` and ``cp`` the outlet
    temperature is the exact exponential profile ``T_out = T_amb + (T_in - T_amb) exp(-NTU)``,
    ``NTU = U pi d L / (m_dot cp)`` (Incropera et al. 2007, Fundamentals of Heat and Mass
    Transfer, 6th ed., Section 8.3, constant external temperature), computed as an exchanger
    with an infinite-capacity ambient (``C_r = 0``). The legacy explicit increment
    ``heat_transfer.pipe_temperature_change`` is its first-order expansion and is not reused
    because it overshoots past ambient when ``NTU > 1``. The heat exchanged leaves as
    ``heat_loss`` (fluid warmer than ambient) or enters as ``heat_absorbed`` (fluid colder), so
    the stream energy audit closes exactly.

    Simplifications: steady state (no fluid or wall heat capacity, no transit time), constant
    fluid properties, uniform ``u_value`` and ambient along the pipe, no fittings (add their
    equivalent length to ``length``), kinetic and pressure energy outside the thermal model.
    Validity: single-phase liquid (free gas raises ``PhysicsRangeError``), forward flow
    (reverse flow raises ``PhysicsRangeError``; wire the pipe in the flow direction), relative
    roughness 1e-6 to 1e-2 and Re up to 1e8 (Swamee–Jain range), ``|elevation_change| <=
    length``. Zero flow has no friction or heat exchange and keeps the static head; the stopped
    stream keeps the inlet temperature, which carries no energy.
    """

    def __init__(self):
        """Declare pipe geometry, heat transfer, ports and hydraulic and thermal outputs."""
        super().__init__()

        # Parameters
        self.length = Parameter(Length, gt=0)
        self.inner_diameter = Parameter(Length, gt=0)
        self.roughness = Parameter(Length, default=COMMERCIAL_STEEL_ROUGHNESS)
        self.elevation_change = Parameter(Elevation)
        self.u_value = Parameter(HeatTransferCoefficient)

        # Inlets
        self.inlet = Inlet(Stream)

        # Boundaries
        self.ambient_temperature = Boundary(Temperature)

        # Outputs
        self.pressure_drop = Output(PressureDifference)
        self.velocity = Output(Speed)
        self.outlet_T = Output(Temperature)
        self.heat_loss = Output(Power)
        self.heat_absorbed = Output(Power)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Apply friction, static head and heat exchange to the inlet stream."""

        # Outlets
        inlet = inlets.inlet
        self._check(inlet)
        rho = inlet.fluid.properties(inlet.p, inlet.T).rho_l
        static = hydraulics.hydrostatic_dp(rho, self.elevation_change)
        outlet_p = inlet.p - self._friction_drop(inlet) - static
        if outlet_p < 0:
            raise PhysicsRangeError(
                f"{self.path}: outlet pressure = {outlet_p} Pa from inlet.p = {inlet.p} Pa; "
                "expected the friction and static drops to leave a nonnegative pressure"
            )
        outlet = inlet.with_(T=self._outlet_temperature(inlet), p=outlet_p)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        outlet = outlets.outlet
        cp = inlet.fluid.properties(inlet.p, inlet.T).cp_l
        heat = inlet.m_dot * cp * (inlet.T - outlet.T)
        self.pressure_drop = inlet.p - outlet.p
        self.velocity = self._velocity(inlet)
        self.outlet_T = outlet.T
        self.heat_loss = max(heat, 0.0)
        self.heat_absorbed = max(-heat, 0.0)

    def _check(self, inlet):
        """Reject a pipe shorter than its rise, reverse flow and free gas."""
        if abs(self.elevation_change) > self.length:
            raise ConfigurationError(
                f"{self.path}: elevation_change = {self.elevation_change} m; expected at most "
                f"length = {self.length} m in magnitude"
            )
        if inlet.m_dot < 0:
            raise PhysicsRangeError(
                f"{self.path}: inlet.m_dot = {inlet.m_dot} kg/s; expected >= 0 (reverse flow is "
                "not modelled; wire the pipe in the flow direction)"
            )
        if inlet.fluid.gas_mass_fraction > 0:
            raise PhysicsRangeError(
                f"{self.path}: inlet.fluid.gas_mass_fraction = "
                f"{inlet.fluid.gas_mass_fraction}; expected 0 (single-phase liquid model)"
            )

    def _velocity(self, inlet):
        """Return the mean liquid velocity [m/s]."""
        rho = inlet.fluid.properties(inlet.p, inlet.T).rho_l
        return inlet.m_dot / (rho * geometry.circle_area(self.inner_diameter))

    def _friction_drop(self, inlet):
        """Return the friction pressure drop [Pa] for laminar, transitional or turbulent flow.

        In the transition range the drop is interpolated linearly in Re between the laminar drop
        at Re = 2300 and the Swamee–Jain drop at Re = 4000.
        """
        properties = inlet.fluid.properties(inlet.p, inlet.T)
        velocity = self._velocity(inlet)
        velocity_per_reynolds = properties.mu_l / (properties.rho_l * self.inner_diameter)
        reynolds = velocity / velocity_per_reynolds
        if reynolds <= LAMINAR_REYNOLDS:
            return self._laminar_drop(velocity, properties)
        if reynolds >= TURBULENT_REYNOLDS:
            return self._turbulent_drop(velocity, properties)
        laminar = self._laminar_drop(LAMINAR_REYNOLDS * velocity_per_reynolds, properties)
        turbulent = self._turbulent_drop(TURBULENT_REYNOLDS * velocity_per_reynolds, properties)
        weight = (reynolds - LAMINAR_REYNOLDS) / (TURBULENT_REYNOLDS - LAMINAR_REYNOLDS)
        return laminar + weight * (turbulent - laminar)

    def _laminar_drop(self, velocity, properties):
        """Return the Hagen–Poiseuille drop ``32 mu L v / D^2`` [Pa], that is ``f = 64/Re``."""
        return 32 * properties.mu_l * self.length * velocity / self.inner_diameter**2

    def _turbulent_drop(self, velocity, properties):
        """Return the Darcy–Weisbach drop [Pa] with the Swamee–Jain friction factor."""
        friction, _ = hydraulics.darcy_weisbach_dp(
            velocity,
            properties.rho_l,
            0.0,
            properties.mu_l,
            self.inner_diameter,
            self.roughness,
            self.length,
        )
        return friction

    def _outlet_temperature(self, inlet):
        """Return the outlet temperature [K] of the exponential ambient-exchange profile."""
        if inlet.m_dot == 0:
            return inlet.T
        capacity_rate = inlet.m_dot * inlet.fluid.properties(inlet.p, inlet.T).cp_l
        conductance = self.u_value * math.pi * self.inner_diameter * self.length
        transfer_units = heat_transfer.ntu(conductance, capacity_rate)
        effectiveness = heat_transfer.effectiveness_parallel(transfer_units, 0.0)
        return inlet.T - effectiveness * (inlet.T - self.ambient_temperature)
