"""Hydrocyclone desander with a quadratic pressure loss and a constant sand removal share."""

from gemini import ops
from gemini.errors import PhysicsRangeError
from gemini.modules.module import Module
from gemini.physics import fluid, hydraulics, separation
from gemini.types import (
    Boundary,
    Fraction,
    Inlet,
    MassConcentration,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    PressureDifference,
    Stream,
)


class Desander(Module):
    """Hydrocyclone desander removing a constant share of the produced sand.

    Hydrocyclones separate solids centrifugally; their grade efficiency depends on particle
    size and density relative to the cut size ``d50`` (Svarovsky, 2000, *Solid-Liquid
    Separation*, 4th ed., chapter "Hydrocyclones"). This model lumps the grade-efficiency curve
    over the produced size distribution into one constant ``separation_efficiency``, so it does
    not follow cut-size changes with flow:

    - liquid volume flow ``Q = m_dot * (1 - x_gas) / rho_l``;
    - ``sand_removal_rate = separation_efficiency * sand_concentration * Q``;
    - ``residual_sand_concentration = (1 - separation_efficiency) * sand_concentration``;
    - ``pressure_drop = dp_nominal * (m_dot / m_dot_nominal) ** 2``, the quadratic law of a
      fixed-geometry cyclone at constant resistance coefficient (as for ``Filter``).

    ``sand_concentration`` is kg of sand per m3 of liquid at the inlet (1 mg/l = 1 g/m3 =
    1e-3 kg/m3). Streams carry no solids, so the liquid mass flow, temperature and fluid pass
    unchanged and the stream balances close exactly; the removed sand is reported as
    ``sand_removal_rate`` only. Pressure loss (of the order of 1 bar at design flow) and
    efficiency are design specific, so all three design values are required. Valid for forward
    flow with a loss below the inlet pressure; otherwise ``PhysicsRangeError`` is raised.
    """

    def __init__(self):
        """Declare desander design data, ports, sand boundary and outputs."""
        super().__init__()

        # Parameters
        self.separation_efficiency = Parameter(Fraction)
        self.dp_nominal = Parameter(PressureDifference, ge=0)
        self.m_dot_nominal = Parameter(MassFlow, gt=0)

        # Inlets
        self.inlet = Inlet(Stream, stream="brine")

        # Boundaries
        self.sand_concentration = Boundary(MassConcentration)

        # Outputs
        self.pressure_drop = Output(PressureDifference, soft_sensor=True)
        self.sand_removal_rate = Output(MassFlow, soft_sensor=True)
        self.residual_sand_concentration = Output(MassConcentration)

        # Outlets
        self.outlet = Outlet(Stream, stream="brine")

    def forward(self, inlets):
        """Apply the quadratic cyclone pressure loss."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet.with_(p=inlet.p - self._pressure_drop(inlet))

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        properties = inlet.fluid.properties(inlet.p, inlet.T)
        liquid_flow = fluid.liquid_volume_flow(inlet.m_dot, properties.gmf, properties.rho_l)
        sand = separation.cyclone_sand(
            self.separation_efficiency, self.sand_concentration, liquid_flow
        )
        self.pressure_drop = self._pressure_drop(inlet)
        self.sand_removal_rate = sand[0]
        self.residual_sand_concentration = sand[1]

    def _pressure_drop(self, inlet):
        """Return the cyclone loss [Pa], quadratic in forward mass flow."""
        ops.check(
            inlet.m_dot >= 0,
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        drop = hydraulics.quadratic_pressure_drop(self.dp_nominal, inlet.m_dot, self.m_dot_nominal)
        ops.check(
            drop <= inlet.p,
            PhysicsRangeError,
            "{path}: pressure_drop = {drop} Pa; expected at most inlet.p = {pressure} Pa",
            path=self.path,
            drop=drop,
            pressure=inlet.p,
        )
        return drop
