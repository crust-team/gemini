"""Flow splitting, gas separation, cyclone sand removal, chemical dosing and filter defaults."""

from gemini import ops

DEFAULT_DEGASSER_DROP = 14900
"""Default pressure loss [Pa] of a degasser vessel, 0.149 bar from Sep_Pin/Sep_Pout of the
original GEMINI example."""

FILTER_NOMINAL_MASS_FLOW = 149 / 3600 * 1068
"""Default clean-filter design flow [kg/s]: 149 m3/h of brine at 1068 kg/m3."""

FILTER_NOMINAL_DROP = 1600
"""Default clean-filter pressure loss [Pa] at the design flow, 0.016 bar of the original GEMINI
example."""

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
    """
    branch = fraction * mass_flow
    return mass_flow - branch, branch


@ops.physics
def degasser_split(
    mass_flow: float, gas_mass_fraction: float, efficiency: float
) -> tuple[float, float, float]:
    """Return the liquid flow, the separated gas flow and the gas fraction left in the liquid.

    ``gas = eta x m``, ``liquid = m - gas`` and ``x_left = (1 - eta) x / (1 - eta x)``.

    Parameters
    ----------
    mass_flow : float
        Inlet mass flow [kg/s].
    gas_mass_fraction : float
        Free gas mass fraction ``x`` of the inlet [-], in [0, 1].
    efficiency : float
        Share ``eta`` of the free gas that leaves through the gas outlet [-], in [0, 1].

    Returns
    -------
    tuple of float
        Liquid outlet mass flow [kg/s], gas outlet mass flow [kg/s] and gas mass fraction of the
        liquid outlet [-]; the free gas is conserved.

    Notes
    -----
    Lumped vessel performance: no residence time, level or solubility (Henry's law); dissolved
    gas stays in the liquid. Retained GEMINI formulation of an ideal split of the free gas.
    """
    liquid, gas = split_flow(mass_flow, efficiency * gas_mass_fraction)
    remaining = (1 - efficiency) * gas_mass_fraction / (1 - efficiency * gas_mass_fraction)
    return liquid, gas, remaining


@ops.physics
def cyclone_sand(
    efficiency: float, sand_concentration: float, liquid_flow: float
) -> tuple[float, float]:
    """Return the sand removal rate and the residual sand concentration of a cyclone.

    ``rate = eta c Q`` and ``c_out = (1 - eta) c``.

    Parameters
    ----------
    efficiency : float
        Lumped separation efficiency ``eta`` over the size distribution [-], in [0, 1].
    sand_concentration : float
        Sand concentration ``c`` of the inlet liquid [kg/m3].
    liquid_flow : float
        Liquid volume flow ``Q`` [m3/s], see ``fluid.liquid_volume_flow``.

    Returns
    -------
    tuple of float
        Sand removal rate [kg/s] and residual concentration [kg/m3].

    Notes
    -----
    The grade-efficiency curve is lumped into one constant efficiency, so the cut size does not
    follow the flow. Reference: Svarovsky (2000), Solid-Liquid Separation, 4th ed., chapter
    "Hydrocyclones"; retained GEMINI formulation.
    """
    return efficiency * sand_concentration * liquid_flow, (1 - efficiency) * sand_concentration


@ops.physics
def dosing_flows(
    dose: float, mass_flow: float, product_concentration: float
) -> tuple[float, float]:
    """Return the product and the active mass flow of a chemical dosing.

    ``m_product = dose m`` and ``m_active = w m_product``.

    Parameters
    ----------
    dose : float
        Mass of product per mass of treated fluid [-] (1 ppm = 1e-6).
    mass_flow : float
        Treated mass flow [kg/s].
    product_concentration : float
        Mass fraction ``w`` of active substance in the product [-].

    Returns
    -------
    tuple of float
        Product mass flow and active substance mass flow [kg/s].

    Notes
    -----
    Mass-proportional dosing as in inhibitor programmes (Gallup, 2009, Geothermics 38,
    326-334); the dosed mass is not added to the stream.
    """
    product = dose * mass_flow
    return product, product_concentration * product
