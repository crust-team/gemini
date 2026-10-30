"""Production temperature decline of a geothermal doublet after thermal breakthrough."""

from gemini import ops
from gemini.errors import PhysicsRangeError
from gemini.modules.module import Module
from gemini.physics import ground
from gemini.types import (
    Boundary,
    Duration,
    Fraction,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    State,
    Stream,
    Temperature,
    TemperatureDifference,
    Volume,
    VolumetricHeatCapacity,
)


class ThermalDecline(Module):
    """Cold-front breakthrough and production temperature decline of a balanced doublet.

    Placed between a ``ProductionReservoir`` sandface and the production well, it lowers the
    produced temperature once the cooled region around the injector reaches the producer.
    The state is the cumulative injected volume V [m3]; in a balanced doublet it equals the
    produced volume, so each step adds the inlet liquid volume flow times ``dt`` (exact for a
    flow that is constant over the step).

    Breakthrough follows Gringarten and Sauty (1975, J. Geophys. Res. 80(35), 4956-4962): the
    thermal front reaches the producer after the injected volume
    V_B = pi L**2 H (rho c)_a / (3 (rho c)_w), with L the ``well_spacing``, H the
    ``aquifer_thickness``, (rho c)_a = phi (rho c)_w + (1 - phi) (rho c)_r and (rho c)_w the
    liquid density times heat capacity of the inlet fluid. ``breakthrough_time`` is V_B / Q at
    the current liquid volume flow Q, counted from the start of injection (``None`` at zero
    flow). After breakthrough the doublet's streamlines arrive one after another: the share
    f = theta / pi of the flow on streamlines whose thermal travel time
    3 (sin theta - theta cos theta) / sin(theta)**3 * t_B has passed arrives at the injection
    temperature (``ground.doublet_cold_fraction``), so
    outlet_T = T_in - f(V / V_B) (T_in - injection_temperature), where T_in is the reservoir
    temperature carried by the inlet.

    Assumptions: homogeneous, isotropic, confined aquifer of constant thickness; fully
    penetrating wells; no regional flow; piston-like displacement with local thermal
    equilibrium between water and rock; no heat recharge from the confining beds (which makes
    the decline an upper bound, adequate when the aquifer is thick compared with the
    conduction length sqrt(alpha t) of the cap and base rock over the operating time); constant
    properties; and the current injection temperature applies to all injected water. Mass and
    pressure pass unchanged. The module is deliberately not first-law closed: the temperature
    drop is a correction of the open aquifer boundary, so the stream audit shows the residual
    m_dot cp (T_in - outlet_T), which is not heat lost to the environment.

    NOTE(refactor): written with ops, but a graph break while the graph has no ``scan``: the
    injected volume is a state.
    """

    def __init__(self):
        """Declare doublet geometry, rock data, the injection boundary and the volume state."""
        super().__init__()

        # Parameters
        self.well_spacing = Parameter(Length, gt=0)
        self.aquifer_thickness = Parameter(Length, gt=0)
        self.porosity = Parameter(Fraction, gt=0, lt=1)
        self.rock_volumetric_heat_capacity = Parameter(VolumetricHeatCapacity)

        # Inlets
        self.inlet = Inlet(Stream, stream="brine")

        # Boundaries
        self.injection_temperature = Boundary(Temperature)

        # States
        self.injected_volume = State(Volume, default=0)

        # Outputs
        self.breakthrough_time = Output(Duration | None)
        self.temperature_drop = Output(TemperatureDifference)
        self.outlet_T = Output(Temperature)

        # Outlets
        self.outlet = Outlet(Stream, stream="brine")

    def forward(self, inlets):
        """Lower the reservoir temperature by the cold-water share of the produced flow."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet.with_(T=inlet.T - self._temperature_drop(inlet))

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        flow = self._liquid_flow(inlet)
        volume = self._breakthrough_volume(inlet)
        self.breakthrough_time = ops.where(flow != 0, volume / flow, None)
        self.temperature_drop = self._temperature_drop(inlet)
        self.outlet_T = outlets.outlet.T

    def _advance_states(self, inlets, outlets, dt):
        flow = self._liquid_flow(inlets.inlet)
        return {"injected_volume": self.injected_volume + flow * dt}

    def _temperature_drop(self, inlet):
        """Return the produced temperature drop [K] at the start-of-step injected volume."""
        self._liquid_flow(inlet)
        ratio = self.injected_volume / self._breakthrough_volume(inlet)
        return ground.doublet_cold_fraction(ratio) * (inlet.T - self.injection_temperature)

    def _breakthrough_volume(self, inlet):
        """Return the Gringarten-Sauty breakthrough volume V_B [m3] for the inlet fluid."""
        fluid = inlet.fluid.properties(inlet.p, inlet.T)
        water = fluid.liquid_volumetric_heat_capacity
        aquifer = ground.aquifer_volumetric_heat_capacity(
            self.porosity, water, self.rock_volumetric_heat_capacity
        )
        return ground.doublet_breakthrough_volume(
            self.well_spacing, self.aquifer_thickness, aquifer, water
        )

    def _liquid_flow(self, inlet):
        """Return the produced liquid volume flow [m3/s]; reverse flow is outside the model."""
        ops.check(
            inlet.m_dot >= 0,
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0 (production)",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        return inlet.m_dot / inlet.fluid.properties(inlet.p, inlet.T).rho_l
