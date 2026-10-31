"""Limits a user sets on the outputs of a run, by path pattern, and the check of each."""

from fnmatch import fnmatchcase

import numpy as np

from gemini.engine.results import PORT_QUANTITIES, port_fields
from gemini.errors import ValidationError
from gemini.physics import units
from gemini.types.flows import FIELD_QUANTITIES
from gemini.types.shapes import check, value
from gemini.utils.strings import close_matches, did_you_mean, join_path, split_path

"""The results column of each stream field."""

TOLERANCE = 1e-9
"""Relative margin of a limit: a value on the limit passes through its rounding; numerical."""


def _split_target(target):
    """Return ``(path pattern, field)``: a port quantity is ``<port>.<quantity>``."""
    head, _, last = target.rpartition(".")
    if last in PORT_QUANTITIES:
        pattern, _, port = head.rpartition(".")
        return pattern, f"{port}.{last}"
    return head, last


class Limits:
    """Limits of ``(path pattern, output, min, max)``, built without a plant.

    ``add("d*.flow", min="50 m3/h", max="300 m3/h")`` takes a pattern of ``fnmatch`` for the
    module path, whose ``*`` stays within one name, and an output name after the last dot. A plant
    is not needed: the pattern is checked against one by ``gm.checks.limits``. The unit of a limit
    is checked here. ``to_dict`` and ``from_dict`` give a plain dictionary, so limits can be stored.
    """

    def __init__(self):
        """Start without limits."""
        self.entries = []

    def add(self, target, min=None, max=None):
        """Add a limit on ``"<path pattern>.<output>"``; give ``min``, ``max`` or both.

        ``<output>`` is an output or a port quantity (``boiler.fluid_out.temperature``).
        """
        pattern, output = _split_target(target)
        if not pattern or not output:
            raise ValidationError(
                f"limits: target = {target!r}; expected '<path pattern>.<output>'",
                path="target",
                code="invalid_value",
            )
        if min is None and max is None:
            raise ValidationError(
                f"limits: {target}: expected min, max or both", path=target, code="missing_value"
            )
        for bound in (min, max):
            _checked(bound)
        self.entries.append({"pattern": pattern, "output": output, "min": min, "max": max})
        return self

    def to_dict(self):
        """Return the limits as plain data."""
        return {"limits": [dict(entry) for entry in self.entries]}

    @classmethod
    def from_dict(cls, data):
        """Return the limits of a dictionary of ``to_dict``, each checked as ``add`` does."""
        limits = cls()
        for entry in data["limits"]:
            limits.add(f"{entry['pattern']}.{entry['output']}", entry["min"], entry["max"])
        return limits


def _checked(bound):
    """Refuse a limit that is neither a number nor a number with a known unit."""
    if isinstance(bound, str):
        _, unit = units.parse(bound)
        units.si_unit(unit)


def _in_unit(bound, unit, quantity):
    """Return a limit in the unit of its output; a number already is."""
    if bound is None or not isinstance(bound, str):
        return bound
    number, given = units.parse(bound)
    return units.convert(number, given, unit, quantity)


def _fits(path, pattern):
    """Return whether a module path fits a pattern, part by part: ``*`` stays within a name."""
    parts, wanted = path.split("."), pattern.split(".")
    return len(parts) == len(wanted) and all(map(fnmatchcase, parts, wanted))


def _matched(plant, entry):
    """Return the paths of the modules a limit matches; none raises ``unknown_name``."""
    paths = [path for path, _ in plant.named_modules() if path]
    matching = [path for path in paths if _fits(path, entry["pattern"])]
    if not matching:
        raise ValidationError(
            f"limits: pattern = {entry['pattern']!r} matches no module"
            f"{did_you_mean(entry['pattern'], paths)}",
            path=entry["pattern"],
            code="unknown_name",
            suggestions=close_matches(entry["pattern"], paths),
        )
    declared = [path for path in matching if entry["output"] in _fields(plant, path)]
    if not declared:
        names = sorted({name for path in matching for name in _fields(plant, path)})
        raise ValidationError(
            f"limits: {entry['pattern']}: no output {entry['output']!r}"
            f"{did_you_mean(entry['output'], names)}",
            path=f"{entry['pattern']}.{entry['output']}",
            code="unknown_name",
            suggestions=close_matches(entry["output"], names),
        )
    return declared


def _fields(plant, path):
    """Return the ``(unit, quantity)`` of what a limit may judge: outputs and port quantities."""
    module = plant.get_module(path)
    outputs = {
        name: (declaration.unit or "-", declaration.quantity)
        for name, declaration in module.outputs(recurse=False).items()
    }
    return outputs | port_fields(module)


def _port_series(frame, module, port, field):
    """Return the column of a stream field of a port, and whether the module carried flow."""
    return _column(frame, module, f"{port}.{FIELD_QUANTITIES[field]}")


def _column(frame, path, name):
    """Return a leaf column over the run and whether its module carried flow, tick by tick."""
    values = frame[join_path(path, name)].to_numpy(dtype=float)
    active = frame[join_path(path, "operating")].to_numpy(dtype=bool)
    return values, active


def _series(plant, frame, path, name):
    """Return ``(values, active)`` of an output: a leaf column, or the combination of a plant.

    ``Results`` holds leaf columns, so an output of a plant is computed from the paths it names,
    and a tick counts when every leaf behind it carried flow.
    """
    if join_path(path, name) in frame:
        return _column(frame, path, name)
    module = plant.get_module(path)
    key, *paths = module.outputs(recurse=False)[name].formula or (None,)
    if key is None:
        raise ValidationError(
            f"limits: {join_path(path, name)}: the results hold no column of this output",
            path=join_path(path, name),
            code="no_value",
        )
    series = [_path_series(plant, frame, path, item) for item in paths]
    active = np.logical_and.reduce([flag for _, flag in series])
    return _combined(key, [values for values, _ in series]), active


def _combined(key, values):
    """Return the arrays of a combination, as a plant computes it on one tick."""
    if key == "sum":
        return np.sum(values, axis=0)
    return values[0] - values[1] if key == "difference" else values[0] / values[1]


def _path_series(plant, frame, path, item):
    """Return ``(values, active)`` of a path of the plant at ``path``."""
    owner, name = split_path(item)
    if not owner:
        return _series(plant, frame, path, name)
    if name in FIELD_QUANTITIES:
        module, port = split_path(join_path(path, owner))
        return _port_series(frame, module, port, name)
    return _series(plant, frame, join_path(path, owner), name)


def _worst(values, lower, upper):
    """Return ``(worst value, passed)``: the value furthest out, or nearest the limit inside."""
    if upper is None:
        worst = float(values.min())
    elif lower is None:
        worst = float(values.max())
    else:
        lowest, highest = float(values.min()), float(values.max())
        worst = lowest if lower - lowest > highest - upper else highest
    margin = TOLERANCE * abs(worst)
    above = lower is None or worst >= lower - margin
    below = upper is None or worst <= upper + margin
    return worst, above and below


def _limit_value(lower, upper, unit):
    """Return the limit as a value: a number, or ``[min, max]`` for both."""
    if lower is None or upper is None:
        return value(upper if lower is None else lower, unit)
    return value([lower, upper], unit)


def _check(plant, frame, path, entry):
    """Return the check of one matched module and output."""
    name = entry["output"]
    unit, quantity = _fields(plant, path)[name]
    lower = _in_unit(entry["min"], unit, quantity)
    upper = _in_unit(entry["max"], unit, quantity)
    values, active = _series(plant, frame, path, name)
    judged = values[active & np.isfinite(values)]
    label = join_path(path, name)
    limit = _limit_value(lower, upper, unit)
    if not judged.size:
        reason = "the module carried no flow in this run"
        return check(label, None, value(None, unit, reason), limit)
    worst, passed = _worst(judged, lower, upper)
    return check(label, passed, value(worst, unit), limit)


def limits(plant, results, limits):
    """Check the ``Limits`` against a finished run; a violated limit is an answer, not an error.

    Each pattern is matched against the module paths of ``plant``, name by name. An output is
    read over the run, a composite's through the leaves its formula names, on the ticks its module
    carried flow: the minimum flow of a doublet holds while it runs.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    results : Results
        A finished run.
    limits : Limits
        The limits to check.

    Returns
    -------
    list of dict
        One check ``{name, passed, value, limit}`` per matched module and output: ``name`` is
        ``<path>.<output>``, ``value`` the worst value of the run and ``limit`` the limit, in the
        unit of the output, an array ``[min, max]`` with both. ``passed`` is ``None``, with the
        reason in ``value``, for a module that carried no flow.

    A pattern that matches no module, or no module with that output, raises ``ValidationError``
    (code ``unknown_name``) with suggestions.
    """
    frame = results.to_frame()
    return [
        _check(plant, frame, path, entry)
        for entry in limits.entries
        for path in _matched(plant, entry)
    ]
