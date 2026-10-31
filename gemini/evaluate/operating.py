"""The time each doublet ran in a finished run."""

import numpy as np

from gemini._utils.strings import join_path
from gemini._utils.time import parse_duration
from gemini.errors import ValidationError
from gemini.plants.doublet import Doublet
from gemini.types.shapes import check, value

FLOW_COLUMN = "reservoir.liquid_flow"
"""The leaf column behind ``Doublet.flow``, below the path of a doublet."""


def operating_time(plant, results, duration):
    """Check that each doublet ran ``duration``, to within half a step.

    A doublet runs during a step when it carried flow in it: its ``reservoir.liquid_flow``, the
    column behind ``Doublet.flow``, is above zero. Its operating time is the sum of the durations
    of those steps. A plan rounds the operating time to whole steps, so a time within half a step
    of ``duration`` passes.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    results : Results
        A finished run, at any step.
    duration : str or float
        The time each doublet has to run: a duration text such as ``"330 d"``, or seconds.

    Returns
    -------
    list of dict
        One check ``{name, passed, value, limit}`` per doublet: ``name`` is
        ``<path>.operating_time``, ``value`` the time it ran and ``limit`` is ``duration``, both
        in ``s``.

    Raises
    ------
    ValidationError
        With code ``invalid_value`` for a ``duration`` that is no positive duration.
    """
    try:
        limit = parse_duration(duration).total_seconds()
    except (TypeError, ValueError) as error:
        raise ValidationError(
            f"checks.operating_time: duration = {duration!r}; expected a positive duration",
            path="duration",
        ) from error
    frame = results.to_frame()
    durations = results.durations
    half_step = float(np.median(durations)) / 2
    doublets = [path for path, module in plant.named_modules() if isinstance(module, Doublet)]
    return [_check(frame, durations, path, limit, half_step) for path in doublets]


def _check(frame, durations, path, limit, half_step):
    """Return the check of the doublet at ``path``."""
    flowing = (frame[join_path(path, FLOW_COLUMN)] > 0).to_numpy()
    ran = float(durations[flowing].sum())
    label = join_path(path, "operating_time")
    return check(label, abs(ran - limit) <= half_step, value(ran, "s"), value(limit, "s"))
