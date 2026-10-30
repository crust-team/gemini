"""Surface pipeline with wall friction, elevation change and heat exchange with its surroundings."""

from gemini import ops
from gemini.errors import ConfigurationError, PhysicsRangeError
from gemini.modules.module import Module
from gemini.physics import geometry, heat_transfer, hydraulics
from gemini.types import (
    Boundary,
    Elevation,
    HeatAbsorbed,
    HeatLoss,
    HeatTransferCoefficient,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    PressureDifference,
    Speed,
    Stream,
    Temperature,
)


class Pipe(Module):
    """Surface pipeline carrying a single-phase liquid, with friction, elevation and heat loss.

    Pressure: ``p_out = p_in - friction_pressure_drop - rho g dz`` with ``dz`` the signed
    ``elevation_change`` from inlet to outlet (positive when the outlet is higher). The
    friction drop is Darcy–Weisbach ``f L/D rho v^2/2``: laminar ``f = 64/Re`` (Hagen–Poiseuille)
    up to Re = 2300, Swamee and Jain (1976, Explicit equations for pipe-flow problems, J. Hydraul.
    Div. ASCE 102) from Re = 4000, and in between a linear interpolation in Re of the friction
    drop at the two limits, a continuous bridge without physical claim for the intermittent
    transition regime; all of it in ``hydraulics.pipe_friction_drop``.

    Heat: the fluid exchanges heat with surroundings at the fixed ``ambient_temperature``
    through the overall coefficient ``heat_transfer_coefficient`` referred to the inner wall area
    ``pi d L`` (the convention of the well path model). With constant ``heat_transfer_coefficient``
    and ``cp`` the outlet temperature is the exact exponential profile ``T_out = T_amb + (T_in -
    T_amb) exp(-NTU)``, ``NTU = U pi d L / (m_dot cp)`` (Incropera et al. 2007, Fundamentals of
    Heat and Mass Transfer, 6th ed., Section 8.3, constant external temperature), computed as an
    exchanger with an infinite-capacity ambient (``C_r = 0``). The legacy explicit increment
    ``heat_transfer.pipe_temperature_change`` is its first-order expansion and is not reused
    because it overshoots past ambient when ``NTU > 1``. The heat exchanged leaves as
    ``heat_loss`` (fluid warmer than ambient) or enters as ``heat_absorbed`` (fluid colder), so
    the stream energy audit closes exactly.

    Simplifications: steady state (no fluid or wall heat capacity, no transit time), constant
    fluid properties, uniform ``heat_transfer_coefficient`` and ambient along the pipe, no fittings
    (add their equivalent length to ``length``), kinetic and pressure energy outside the thermal
    model. Validity: single-phase liquid (free gas raises ``PhysicsRangeError``), forward flow
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
        self.roughness = Parameter(Length, default=hydraulics.COMMERCIAL_STEEL_ROUGHNESS)
        self.elevation_change = Parameter(Elevation)
        self.heat_transfer_coefficient = Parameter(HeatTransferCoefficient)

        # Inlets
        self.inlet = Inlet(Stream)

        # Boundaries
        self.ambient_temperature = Boundary(Temperature)

        # Outputs
        self.pressure_drop = Output(PressureDifference)
        self.velocity = Output(Speed)
        self.outlet_T = Output(Temperature)
        self.heat_loss = Output(HeatLoss)
        self.heat_absorbed = Output(HeatAbsorbed)

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
        ops.check(
            outlet_p >= 0,
            PhysicsRangeError,
            "{path}: outlet pressure = {outlet_p} Pa from inlet.p = {inlet_p} Pa; "
            "expected the friction and static drops to leave a nonnegative pressure",
            path=self.path,
            outlet_p=outlet_p,
            inlet_p=inlet.p,
        )
        outlet = inlet.with_(T=self._outlet_temperature(inlet), p=outlet_p)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        outlet = outlets.outlet
        heat = heat_transfer.heat_rate(inlet.heat_capacity_rate(), inlet.T - outlet.T)
        loss, absorbed = heat_transfer.signed_parts(heat)
        self.pressure_drop = inlet.p - outlet.p
        properties = inlet.fluid.properties(inlet.p, inlet.T)
        self.velocity = geometry.mean_velocity(inlet.m_dot, properties.rho_l, self.inner_diameter)
        self.outlet_T = outlet.T
        self.heat_loss = loss
        self.heat_absorbed = absorbed

    def _check(self, inlet):
        """Reject a pipe shorter than its rise, reverse flow and free gas."""
        ops.check(
            ops.abs(self.elevation_change) <= self.length,
            ConfigurationError,
            "{path}: elevation_change = {elevation_change} m; expected at most "
            "length = {length} m in magnitude",
            path=self.path,
            elevation_change=self.elevation_change,
            length=self.length,
        )
        ops.check(
            inlet.m_dot >= 0,
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0 (reverse flow is "
            "not modelled; wire the pipe in the flow direction)",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        if inlet.fluid.gas_mass_fraction > 0:
            raise PhysicsRangeError(
                f"{self.path}: inlet.fluid.gas_mass_fraction = "
                f"{inlet.fluid.gas_mass_fraction}; expected 0 (single-phase liquid model)"
            )

    def _friction_drop(self, inlet):
        """Return the friction pressure drop [Pa] for laminar, transitional or turbulent flow."""
        properties = inlet.fluid.properties(inlet.p, inlet.T)
        velocity = geometry.mean_velocity(inlet.m_dot, properties.rho_l, self.inner_diameter)
        return hydraulics.pipe_friction_drop(
            velocity,
            properties.rho_l,
            properties.mu_l,
            self.inner_diameter,
            self.roughness,
            self.length,
        )

    def _outlet_temperature(self, inlet):
        """Return the outlet temperature [K] of the exponential ambient-exchange profile."""
        conductance = hydraulics.pipe_conductance(
            self.heat_transfer_coefficient, self.inner_diameter, self.length
        )
        effectiveness = heat_transfer.ambient_effectiveness(conductance, inlet.heat_capacity_rate())
        return heat_transfer.effectiveness_outlet_temperature(
            inlet.T, effectiveness, self.ambient_temperature
        )
