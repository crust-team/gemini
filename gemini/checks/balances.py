"""Energy and mass ledgers over the time series of a finished run."""

import numpy as np

from gemini.backends import settings
from gemini.engine.chunks import PathColumns
from gemini.modules._utils import balance
from gemini.modules.plants.plan import inner_ends, is_plant, leaf_ends
from gemini.types.results import ModuleResult
from gemini.types.shapes import check, value
from gemini.utils.strings import join_path

ENERGY_TOLERANCE = 1e-9
"""Smallest negative power [W] still read as zero."""

MASS_TOLERANCE = 1e-12
"""Smallest negative mass flow [kg/s] still read as zero."""

MODULE_TOLERANCE = 1e-9
"""Largest relative residual of a module, in or out, the larger of the two; numerical."""

PLANT_TOLERANCE = 1e-6
"""Largest relative residual of the root; numerical, the iterations of a loop stop near it."""

_NONNEGATIVE_ENERGY = ("fuel", "power_in", "power_out")
"""The energy columns that are nonnegative; ``loss_out`` and ``heat_accumulation`` are signed."""


def _columns(results, wanted):
    """Return the result columns for which ``wanted(path, field)`` holds, as a frame."""
    frame = results.to_frame()
    names = [
        join_path(path, field)
        for path, fields in results.names().items()
        for field in fields
        if wanted(path, field)
    ]
    return frame[names]


def _nonnegative(name, values, tolerance, unit, absent):
    """Judge that every value is finite-or-missing and at least ``-tolerance`` in ``unit``."""
    limit = value(tolerance, unit)
    if values.shape[1] == 0:
        return check(name, None, value(None, unit, absent), limit)
    array = values.to_numpy(dtype=float)
    if np.isnan(array).all():
        return check(name, None, value(None, unit, "every value is missing"), limit)
    smallest = float(np.nanmin(array))
    passed = bool(smallest >= -tolerance and not np.isinf(array).any())
    return check(name, passed, value(smallest, unit), limit)


def energy_balance(results):
    """Check the energy ledger of a finished run: the energy outputs have their sign.

    It reads every leaf column named ``power_in``, ``power_out`` or ``fuel`` and checks that each
    value is finite or missing and not negative beyond the tolerance (``loss_out`` and
    ``heat_accumulation`` are signed and are not judged). ``plant_balance`` checks the closure.

    Parameters
    ----------
    results : Results
        A finished run; the plant is not needed.

    Returns
    -------
    dict
        ``{name: "energy_balance", passed, value, limit}``: ``value`` is the smallest of those
        powers [W] over all columns and ticks, ``limit`` is 1e-9 W and ``passed`` is whether
        ``value >= -limit`` with no infinite value. ``passed`` is ``None``, with a ``reason`` in
        ``value``, when no such column, or no value, exists.
    """
    values = _columns(results, lambda path, field: field in _NONNEGATIVE_ENERGY)
    return _nonnegative(
        "energy_balance", values, ENERGY_TOLERANCE, "W", "results have no energy output column"
    )


def mass_balance(results):
    """Check the mass-flow ledger of a finished run: no mass flow is negative or infinite.

    It covers the columns whose unit in ``results.units`` is kg/s (for example
    ``degasser.gas_out.mass_flow``): each value must be finite or missing and not negative beyond
    the tolerance. ``plant_balance`` checks the closure.

    Parameters
    ----------
    results : Results
        A finished run; the plant is not needed.

    Returns
    -------
    dict
        ``{name: "mass_balance", passed, value, limit}``: ``value`` is the smallest mass flow
        [kg/s], ``limit`` 1e-12 kg/s. ``passed`` is ``None``, with a ``reason`` in ``value``, when
        no output has the unit kg/s, or no value exists.
    """
    values = _columns(results, lambda path, field: results.unit(path, field) == "kg/s")
    absent = "results have no output in kg/s"
    return _nonnegative("mass_balance", values, MASS_TOLERANCE, "kg/s", absent)


def _call_columns(result):
    """Return the columns of one module call and of the leaves below it, as a run has them."""
    calls = result.leaves() | {"": result}
    return {
        join_path(path, field): column
        for path, call in calls.items()
        for field, column in PathColumns.of(call, None, [True]).columns.items()
    }


def _run_columns(results):
    """Return the columns of a finished run."""
    frame = results.to_frame()
    return {name: frame[name] for name in frame.columns}


def _reader(run):
    """Return ``read(path, field)``: a column as an array, or zero when the run has none."""
    columns = _call_columns(run) if isinstance(run, ModuleResult) else _run_columns(run)

    def read(path, field):
        name = join_path(path, field)
        return np.asarray(columns[name], dtype=float) if name in columns else 0.0

    return read


def _closure(name, incoming, outgoing, unresolved, tolerance):
    """Return the check that ``incoming - outgoing - unresolved`` is small against the flows."""
    limit = value(tolerance, "-")
    residual = np.abs(np.asarray(incoming - outgoing - unresolved, dtype=float))
    relative = residual / np.asarray(balance.scale(incoming, outgoing), dtype=float)
    if relative.size == 0 or np.isnan(relative).all():
        return check(name, None, value(None, "-", "every value is missing"), limit)
    worst = float(np.nanmax(relative))
    return check(name, worst <= tolerance, value(worst, "-"), limit)


def _root_ends(plant, run, section):
    """Return the ends ``(path, port)`` of the ports of the root in ``section``.

    A call shows them on the root; a run holds leaves, so they are the leaf ports they reach.
    """
    if isinstance(run, ModuleResult):
        return [("", name) for name in getattr(plant, f"_{section}")]
    if not is_plant(plant):
        return []
    names = plant._port_map(section)
    inner = [end for name in names for end in inner_ends(plant, "", section, name)]
    return [leaf for end in inner for leaf in leaf_ends(plant, end, section)]


def _module_checks(path, module, read):
    """Return the mass and the energy check of one leaf over a run."""
    ledger = balance.column_ledger(module, lambda field: read(path, field))
    incoming, outgoing = balance.leaf_mass(module, ledger)
    audit = balance.leaf_energy(module, ledger)
    unresolved = audit["unresolved_power"] + balance.flow_work(module, ledger)
    return [
        _closure(f"{path} mass", incoming, outgoing, 0.0, MODULE_TOLERANCE),
        _closure(f"{path} energy", audit["in"], audit["out"], unresolved, MODULE_TOLERANCE),
    ]


def plant_balance(plant, run):
    """Check that mass and energy close for every module and for the whole plant.

    For a leaf, what enters equals what leaves through its ports, with the losses and the change
    of stored energy, within 1e-9 of the larger flow. For the root, in and out are the ports of
    the grids and environment modules, within 1e-6 (``balance.plant_totals`` says what else
    counts). Results hold the tick a module ran; a run the plant did not wire, such as a replay,
    does not close at the root.

    Parameters
    ----------
    plant : Module
        The plant that produced ``results``.
    run : Results or ModuleResult
        A finished run, or one call of ``plant``.

    Returns
    -------
    list of dict
        One check ``{name, passed, value, limit}`` per ``"<path> mass"`` and ``"<path> energy"``,
        then ``"plant mass"`` and ``"plant energy"``; ``value`` is the worst relative residual
        over the ticks. ``passed`` is ``None`` with a ``reason`` when no tick has a value.
    """
    read = _reader(run)
    with settings(backend="numpy"):
        return _module_and_plant_checks(plant, run, read)


def _module_and_plant_checks(plant, run, read):
    """Return the checks of every leaf, then of the root; columns are arrays on every backend."""
    checks = []
    for path, module in plant.named_modules():
        if module.is_leaf and path:
            checks.extend(_module_checks(path, module, read))
    ends = {section: _root_ends(plant, run, section) for section in ("inlets", "outlets")}
    totals = balance.plant_totals(plant, ends, read)
    checks.append(
        _closure("plant mass", totals["mass_in"], totals["mass_out"], 0.0, PLANT_TOLERANCE)
    )
    checks.append(
        _closure(
            "plant energy",
            totals["energy_in"],
            totals["energy_out"],
            totals["unresolved"],
            PLANT_TOLERANCE,
        )
    )
    return checks
