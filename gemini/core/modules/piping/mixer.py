"""Adiabatic junction mixing two streams of the same fluid."""

from gemini.core.modules.module import Module
from gemini.core.types import Inlet, Outlet, Output, PressureDifference, Stream, Temperature
from gemini.errors import ConfigurationError, PhysicsRangeError


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

    Streams of different fluids raise ``ConfigurationError`` (a mixture property model would be
    needed); reverse flow in either inlet raises ``PhysicsRangeError``.
    """

    def __init__(self):
        """Declare both inlets, the mixed outlet and the mixing diagnostics."""
        super().__init__()

        # Inlets
        self.first_in = Inlet(Stream)
        self.second_in = Inlet(Stream)

        # Outputs
        self.mixed_out_T = Output(Temperature)
        self.pressure_imbalance = Output(PressureDifference)

        # Outlets
        self.mixed_out = Outlet(Stream)

    def forward(self, inlets):
        """Combine both inlet streams at the lower inlet pressure."""

        # Outlets
        first_in = inlets.first_in
        second_in = inlets.second_in
        self._check(first_in, second_in)
        mixed_out = first_in.with_(
            m_dot=first_in.m_dot + second_in.m_dot,
            T=self._mixed_temperature(first_in, second_in),
            p=min(first_in.p, second_in.p),
        )

        outlets = dict(mixed_out=mixed_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.mixed_out_T = outlets.mixed_out.T
        self.pressure_imbalance = abs(inlets.first_in.p - inlets.second_in.p)

    def _check(self, first_in, second_in):
        """Reject reverse flow and streams of different fluids."""
        if first_in.m_dot < 0 or second_in.m_dot < 0:
            raise PhysicsRangeError(
                f"{self.path}: first_in.m_dot = {first_in.m_dot} kg/s, second_in.m_dot = "
                f"{second_in.m_dot} kg/s; expected both >= 0"
            )
        if first_in.fluid != second_in.fluid:
            raise ConfigurationError(
                f"{self.path}: first_in.fluid = {first_in.fluid!r}, second_in.fluid = "
                f"{second_in.fluid!r}; expected the same fluid"
            )

    def _mixed_temperature(self, first_in, second_in):
        """Return the adiabatic mixing temperature [K] weighted by heat capacity rates."""
        first_rate = first_in.m_dot * first_in.fluid.properties(first_in.p, first_in.T).cp_l
        second_rate = second_in.m_dot * second_in.fluid.properties(second_in.p, second_in.T).cp_l
        if first_rate + second_rate == 0:
            return (first_in.T + second_in.T) / 2
        return (first_rate * first_in.T + second_rate * second_in.T) / (first_rate + second_rate)
