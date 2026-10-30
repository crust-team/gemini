"""Plant-level time series read from the leaf columns of a finished run."""

import numpy as np

from gemini.core.modules.module import Module
from gemini.utils.strings import join_path


def window_seconds(results):
    """Return the duration [s] of every completed tick of ``results``, as an array."""
    return np.asarray(results.to_dict()["duration"], dtype=float)


def leaf_total(plant, frame, field, module_class=Module):
    """Return the sum of output ``field`` over the leaves of ``module_class`` as a series.

    Parameters
    ----------
    plant : Module
        The plant whose leaves declare the output.
    frame : pandas.DataFrame
        ``results.to_frame()``: one ``path.field`` column per leaf output, in the unit the leaf
        declares.
    field : str
        Output name, such as ``"heat_supplied"``.
    module_class : type, optional
        Only leaves that are instances of this class count; every leaf by default.

    Returns
    -------
    pandas.Series or None
        The sum on the result time index, in the unit of the field. A tick where no summed
        column has a value is NaN. ``None`` when no leaf of the class declares the field or
        none of them ran. The sum adds the descendant leaves' same-named outputs, the rule of a
        plant's automatic sum outputs.
    """
    columns = [
        join_path(path, field)
        for path, module in plant.named_modules()
        if module.is_leaf
        and isinstance(module, module_class)
        and field in module.outputs(recurse=False)
        and join_path(path, field) in frame
    ]
    if not columns:
        return None
    return frame[columns].sum(axis=1, min_count=1)


def results_total(results, frame, field):
    """Return the sum of output ``field`` over every path of ``results`` that has it.

    ``frame`` is ``results.to_frame()``. The result is a series in the unit of the field, NaN on
    a tick where no summed column has a value, or ``None`` when no path has the field.
    """
    columns = [
        join_path(path, field) for path, fields in results.names().items() if field in fields
    ]
    if not columns:
        return None
    return frame[columns].sum(axis=1, min_count=1)


def energy(power, seconds):
    """Return the energy [J] of a power series [W] over tick durations [s], skipping NaN ticks."""
    return float(np.nansum(power.to_numpy(dtype=float) * seconds))
