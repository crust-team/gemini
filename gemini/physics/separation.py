"""Flow splitting, gas separation, cyclone sand removal, chemical dosing and filter defaults."""

from gemini import ops

FILTER_CLOGGING_BAR = 0.5
"""Default clogging pressure-loss limit [bar] of a filter, also that of an old project."""


@ops.physics
def split_flow(mass_flow: float, fraction: float) -> tuple[float, float]:
    """Return the remainder and the branch of a mass flow split, ``(m - f m, f m)``.

    Parameters
    ----------
    mass_flow : float
        Feed mass flow [kg/s].
    fraction : float
        Share of the feed that goes to the branch [-], in [0, 1].

    Returns
    -------
    tuple of float
        Remaining mass flow and branch mass flow [kg/s]; they sum to the feed.

    Notes
    -----
    Ideal tee or bleed with a commanded share and no pressure loss; the sum closes to rounding.
    Valid for any real flow, a reverse flow scales both parts.

    Source: A plain mass balance; no published source is needed.
    """
    branch = fraction * mass_flow
    return mass_flow - branch, branch
