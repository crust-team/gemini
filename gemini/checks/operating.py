"""The days each doublet ran in a finished run."""

from gemini.modules.plants.doublet import Doublet
from gemini.types.shapes import check, value
from gemini.utils.strings import join_path

FLOW_COLUMN = "reservoir.liquid_flow"
"""The leaf column behind ``Doublet.flow``, below the path of a doublet."""


def operating_days(plant, results, days):
    """Check that each doublet ran ``days`` days.

    A doublet runs on a UTC day when it carried flow on that day: its ``reservoir.liquid_flow``,
    the column behind ``Doublet.flow``, is above zero on a tick of the day.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    results : Results
        A finished run.
    days : int
        The days each doublet has to run.

    Returns
    -------
    list of dict
        One check ``{name, passed, value, limit}`` per doublet: ``name`` is
        ``<path>.operating_days``, ``value`` the days it ran and ``limit`` is ``days``, both in
        ``day``; it passes on exactly ``days`` days.
    """
    frame = results.to_frame()
    doublets = [path for path, module in plant.named_modules() if isinstance(module, Doublet)]
    return [_check(frame, path, days) for path in doublets]


def _check(frame, path, days):
    """Return the check of the doublet at ``path``."""
    flowing = frame[join_path(path, FLOW_COLUMN)] > 0
    ran = int(flowing.groupby(frame.index.normalize()).any().sum())
    label = join_path(path, "operating_days")
    return check(label, ran == days, value(ran, "day"), value(days, "day"))
