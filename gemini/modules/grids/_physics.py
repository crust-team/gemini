"""Physics of the grids: the electricity exchange through a connection of limited capacity."""

from dataclasses import dataclass

from gemini import ops


@dataclass(frozen=True)
class GridExchange:
    """Powers [W] of a grid connection."""

    net_import: float
    net_export: float
    unserved_consumption: float
    curtailed_generation: float


@ops.physics
def net_exchange(consumption: float, generation: float, import_limit, export_limit) -> GridExchange:
    """Return the import and export of a plant through a limited grid connection.

    Parameters
    ----------
    consumption, generation : float
        Plant electricity consumption and generation [W], nonnegative.
    import_limit, export_limit : float or None
        Connection limits [W]; ``None`` means unlimited. Whether a limit exists is a
        configuration, not a value, so it is a Python test.

    Returns
    -------
    GridExchange
        ``net_import`` min(max(0, C - G), limit) and ``net_export`` min(max(0, G - C), limit)
        [W]; ``unserved_consumption`` and ``curtailed_generation``, the parts above the limits
        [W].

    Notes
    -----
    Net metering at one connection point, without reactive power, losses or demand charges.

    Source: A plain power balance at the connection point; no published source is needed.
    """
    demand = ops.maximum(0.0, consumption - generation)
    surplus = ops.maximum(0.0, generation - consumption)
    net_import = demand if import_limit is None else ops.minimum(demand, import_limit)
    net_export = surplus if export_limit is None else ops.minimum(surplus, export_limit)
    return GridExchange(
        net_import=net_import,
        net_export=net_export,
        unserved_consumption=demand - net_import,
        curtailed_generation=surplus - net_export,
    )
