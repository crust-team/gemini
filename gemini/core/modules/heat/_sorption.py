"""Helpers the absorption and adsorption machines share: circuit rates and outlet temperatures."""

from gemini import ops
from gemini.errors import PhysicsRangeError


def rates(path, inlets):
    """Return each inlet's heat capacity rate m_dot * cp [W/K]; reject negative flow."""
    rate_of = {}
    for port, stream in inlets.items():
        ops.check(
            stream.m_dot >= 0,
            PhysicsRangeError,
            "{path}: {port}.m_dot = {m_dot} kg/s; expected >= 0",
            path=path,
            port=port,
            m_dot=stream.m_dot,
        )
        rate_of[port] = stream.heat_capacity_rate()
    return rate_of


def outlet_T(stream, rate, duty):
    """Return the outlet temperature [K] after adding ``duty`` [W] at capacity rate ``rate``."""
    return ops.where(duty == 0, stream.T, stream.T + duty / rate)
