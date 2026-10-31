"""Adiabatic junction mixing two streams of the same fluid."""

from gemini import ops
from gemini.errors import PhysicsError, ValidationError
from gemini.modules.module import Module
from gemini.physics import heat_transfer
from gemini.types import Inlet, Outlet, Output, PressureDifference, Stream


class Mixer(Module):
    """Adiabatic tee mixing two streams of one fluid into a single outlet.

    Steady first law without heat or work: ``T_mix = (m_1 cp_1 T_1 + m_2 cp_2 T_2) / (m_1 cp_1 +
    m_2 cp_2)`` and ``m_mix = m_1 + m_2``, so mass and sensible energy close to rounding. A
    stopped junction (both flows zero) carries no energy and takes the mean inlet temperature.

    The outlet pressure is the lower inlet pressure. A junction has one pressure, so in the
    real network the higher-pressure branch is throttled down to it by its own resistance (a
    valve, the tee loss); a sequential model that does not solve the network cannot raise the
    lower stream, and taking the lower pressure never creates pressure energy. The discarded
    difference is reported as ``pressure_imbalance``: a large value means the upstream branches
    are not hydraulically balanced and the model under-predicts a throttling loss upstream.

    Streams of different fluids raise ``ValidationError`` (a mixture property model would be
    needed); reverse flow in either inlet raises ``PhysicsError``.
    """

    def __init__(self):
        """Declare both inlets, the mixed outlet and the mixing diagnostics."""
        super().__init__()

        # Inlets
        self.branch1_in = Inlet(Stream)
        self.branch2_in = Inlet(Stream)

        # Outputs
        self.pressure_imbalance = Output(PressureDifference)

        # Outlets
        self.fluid_out = Outlet(Stream)

    def forward(self, inlets):
        """Combine both inlet streams at the lower inlet pressure."""

        # Outlets
        branch1_in = inlets.branch1_in
        branch2_in = inlets.branch2_in
        self._check(branch1_in, branch2_in)
        fluid_out = branch1_in.with_(
            m_dot=branch1_in.m_dot + branch2_in.m_dot,
            T=self._mixed_temperature(branch1_in, branch2_in),
            p=ops.minimum(branch1_in.p, branch2_in.p),
        )

        outlets = dict(fluid_out=fluid_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.pressure_imbalance = ops.abs(inlets.branch1_in.p - inlets.branch2_in.p)

    def _check(self, branch1_in, branch2_in):
        """Reject reverse flow and streams of different fluids."""
        ops.check(
            ops.logical_and(branch1_in.m_dot >= 0, branch2_in.m_dot >= 0),
            PhysicsError,
            "{path}: branch1_in.m_dot = {first_m_dot} kg/s, branch2_in.m_dot = "
            "{second_m_dot} kg/s; expected both >= 0",
            path=self.path,
            first_m_dot=branch1_in.m_dot,
            second_m_dot=branch2_in.m_dot,
        )
        if branch1_in.fluid != branch2_in.fluid:
            raise ValidationError(
                f"{self.path}: branch1_in.fluid = {branch1_in.fluid!r}, branch2_in.fluid = "
                f"{branch2_in.fluid!r}; expected the same fluid",
                code="invalid_design",
            )

    def _mixed_temperature(self, branch1_in, branch2_in):
        """Return the adiabatic mixing temperature [K] weighted by heat capacity rates."""
        return heat_transfer.mixed_temperature(
            branch1_in.heat_capacity_rate(),
            branch1_in.T,
            branch2_in.heat_capacity_rate(),
            branch2_in.T,
        )
