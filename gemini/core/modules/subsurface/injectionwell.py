"""Injection well from the wellhead down to the sandface."""

from gemini import ops
from gemini.core.modules.subsurface.well import _Well
from gemini.core.types import (
    HeatLoss,
    Inlet,
    Outlet,
    Output,
    Pressure,
    PressureDifference,
    Stream,
    Temperature,
)


class InjectionWell(_Well):
    """Injection-well pressure and temperature profile with integrity checks.

    NOTE(refactor): legacy injection DPDT uses negative flow; the traversal retains that sign
    convention internally while the ports preserve the incoming mass-flow sign.

    NOTE(refactor): the physics is written with ops and runs on arrays, but the module is a
    graph break while the graph cannot carry the ``section_pressure`` and ``section_temperature``
    list outputs.
    """

    flow_direction = "down"

    def __init__(self):
        """Declare injection-well geometry, inlet and outputs."""
        super().__init__()

        # Inlets
        self.wellhead = Inlet(Stream)

        # Outputs
        self.bottomhole_pressure = Output(Pressure, soft_sensor=True)
        self.bottomhole_temperature = Output(Temperature)
        self.dp_friction = Output(PressureDifference)
        self.dp_gravity = Output(PressureDifference)
        self.section_pressure = Output(list[Pressure])
        self.section_temperature = Output(list[Temperature])
        self.heat_loss = Output(HeatLoss)

        # Outlets
        self.bottom = Outlet(Stream)

    def forward(self, inlets):
        """Traverse the injection path with the legacy negative flow convention."""

        # Outlets
        wellhead = inlets.wellhead
        stream = self._traversal_stream(wellhead)
        result = self.traverse(stream, 0, self.pipe_path.total_length, "down")
        a, b = self.correction_factors

        bottom = stream.with_(
            p=a * result.p_out + b,
            T=result.T_out,
            m_dot=wellhead.m_dot,
        )

        outlets = dict(bottom=bottom)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        wellhead = inlets.wellhead
        bottom = outlets.bottom
        stream = self._traversal_stream(wellhead)
        result = self.traverse(stream, 0, self.pipe_path.total_length, "down")
        self.bottomhole_pressure = bottom.p
        self.bottomhole_temperature = bottom.T
        self.dp_friction = result.dp_friction
        self.dp_gravity = result.dp_gravity
        self.section_pressure = result.section_pressure
        self.section_temperature = result.section_temperature
        self.heat_loss = (
            bottom.m_dot * stream.fluid.properties(stream.p, stream.T).cp_l * (stream.T - bottom.T)
        )

    def _traversal_stream(self, stream):
        """Return the stream with the negative flow the legacy injection DPDT expects."""
        return stream.with_(m_dot=-ops.abs(stream.m_dot))
