"""Plant-level time series read from the leaf columns of a finished run."""

import numpy as np

from gemini._utils.strings import join_path
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.module import Module


def window_seconds(results):
    """Return the duration [s] of every completed tick of ``results``, as an array."""
    return results.durations


def leaf_total(plant, frame, field, module_class=Module):
    """Return the sum of declared output ``field`` over the leaves of ``module_class``.

    Parameters
    ----------
    plant : Module
        The plant whose leaves declare the output.
    frame : pandas.DataFrame
        ``results.to_frame()``: one ``path.field`` column per leaf output, in the unit the leaf
        declares.
    field : str
        Output name, such as ``"unmet_demand"``.
    module_class : type, optional
        Only leaves that are instances of this class count; every leaf by default.

    Returns
    -------
    pandas.Series or None
        The sum on the result time index, in the unit of the field. A tick where no summed
        column has a value is NaN. ``None`` when no leaf of the class declares the field or
        none of them ran.
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


def port_difference(plant, frame, module_class, first, second):
    """Return the sum over leaves of ``module_class`` of port field ``first`` less ``second``.

    Fields are ``<port>.<quantity>``: what a grid delivers is what its water loses between its
    ports. ``None`` when no such leaf ran. A tick where a column has no value is NaN.
    """
    paths = [
        path
        for path, module in plant.named_modules()
        if module.is_leaf and isinstance(module, module_class) and join_path(path, first) in frame
    ]
    if not paths:
        return None
    return sum(frame[join_path(path, first)] - frame[join_path(path, second)] for path in paths)


def delivered_heat(plant, frame):
    """Return the heat delivered [W]: what the water loses across the ``HeatingGrid`` leaves."""
    return port_difference(
        plant, frame, HeatingGrid, "supply_in.enthalpy_flow", "return_out.enthalpy_flow"
    )


def delivered_cold(plant, frame):
    """Return the cold delivered [W]: what the water gains across the ``CoolingGrid`` leaves."""
    return port_difference(
        plant, frame, CoolingGrid, "return_out.enthalpy_flow", "supply_in.enthalpy_flow"
    )


def useful_heat(plant, frame):
    """Return the useful heat [W]: what the ``HeatingGrid`` leaves took, at most their demand."""
    delivered = delivered_heat(plant, frame)
    surplus = leaf_total(plant, frame, "surplus", HeatingGrid)
    return delivered if surplus is None or delivered is None else delivered - surplus


def useful_cold(plant, frame):
    """Return the useful cold [W]: what the ``CoolingGrid`` leaves took, at most their demand."""
    delivered = delivered_cold(plant, frame)
    surplus = leaf_total(plant, frame, "surplus", CoolingGrid)
    return delivered if surplus is None or delivered is None else delivered - surplus


def edge_total(plant, frame, field, module_class):
    """Return the sum of column ``field`` over the leaves of ``module_class``, or ``None``."""
    columns = [
        join_path(path, field)
        for path, module in plant.named_modules()
        if module.is_leaf and isinstance(module, module_class) and join_path(path, field) in frame
    ]
    return frame[columns].sum(axis=1, min_count=1) if columns else None


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
