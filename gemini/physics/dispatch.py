"""The daily energy balance of a schedule: what each doublet runs at for a heat need.

These are design-value estimates with no simulation inside; they run on arrays over the days.
"""

from gemini import ops


@ops.physics
def doublet_flow(heat_need, heat_per_flow, minimum_flow, maximum_flow):
    """Return the volume flow of a doublet for a heat need, and the need it leaves.

    Parameters
    ----------
    heat_need : float
        Heat still needed [W], nonnegative.
    heat_per_flow : float
        Heat of a unit volume flow at the allowed brine cooling [J/m3], positive.
    minimum_flow, maximum_flow : float
        Flow limits of an active doublet [m3/s].

    Returns
    -------
    tuple of float
        ``(flow, remaining)``: the flow that gives the need, clipped to the limits, and zero
        without a need; below the minimum flow a doublet runs at the minimum with less cooling.
        ``remaining`` is the need the doublet does not cover [W].

    Notes
    -----
    The rule of thumb of the task: geothermal heat first, doublets in order.

    Validity: Positive limits with ``minimum_flow <= maximum_flow``.
    Source: A plain energy balance; no published source is needed.
    """
    wanted = ops.minimum(ops.maximum(heat_need / heat_per_flow, minimum_flow), maximum_flow)
    flow = ops.where(heat_need > 0, wanted, 0.0)
    return flow, ops.maximum(heat_need - flow * heat_per_flow, 0.0)


@ops.physics
def units_taken(demand, capacities):
    """Return what each unit takes of a demand, in order, each up to its capacity.

    Parameters
    ----------
    demand : float
        Demand [W], nonnegative.
    capacities : list of float
        Capacity of each unit [W], in the order they are asked.

    Returns
    -------
    list of float
        The part of the demand each unit takes [W]; what is left over goes unserved.

    Notes
    -----
    Validity: Nonnegative inputs.
    Source: A plain merit order; no published source is needed.
    """
    taken = []
    left = demand
    for capacity in capacities:
        share = ops.minimum(left, capacity)
        taken.append(share)
        left = left - share
    return taken


@ops.physics
def temperature_after(start, end, share):
    """Return the temperature [K] of a water that went ``share`` of the way from start to end.

    Parameters
    ----------
    start, end : float
        Temperatures [K] at the two ends of a duty.
    share : float
        Part of the duty done [-], in [0, 1].

    Returns
    -------
    float
        ``start + share (end - start)``: at a constant flow and heat capacity the temperature
        moves in proportion to the duty.

    Notes
    -----
    Validity: Constant flow and specific heat over the duty.
    Source: The steady heat balance of a stream; no published source is needed.
    """
    return start + share * (end - start)


@ops.physics
def circuit_flow(heat, specific_heat, temperature_difference):
    """Return the mass flow [kg/s] of a water circuit that carries a heat rate.

    Parameters
    ----------
    heat : float
        Heat rate [W], nonnegative.
    specific_heat : float
        Specific heat [J/kg/K], positive.
    temperature_difference : float
        Supply and return difference [K], positive.

    Returns
    -------
    float
        ``m = Q / (cp dT)``.

    Notes
    -----
    Reference: the steady hydronic heat balance, ASHRAE Handbook, HVAC Systems and Equipment
    (2020), chapter 13.

    Validity: Liquid circuits at constant specific heat.
    Source: As in the reference.
    """
    return heat / (specific_heat * temperature_difference)


@ops.physics
def flow_share(first, second):
    """Return the share [-] of the first of two flows; one when both are zero.

    Parameters
    ----------
    first, second : float
        Flows or heat rates of the two branches, nonnegative.

    Returns
    -------
    float
        ``first / (first + second)``, in [0, 1].

    Notes
    -----
    Validity: Nonnegative inputs.
    Source: A plain ratio; no published source is needed.
    """
    return ops.where(first + second > 0, ops.truediv(first, first + second), 1.0)
