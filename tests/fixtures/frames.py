"""Read a results table by module path and field, as tests compare it with reference tables."""

import pandas as pd

from gemini.utils.strings import split_path

PORT_COLUMNS = {
    ("degasser", "gas_mass_flow"): ("degasser.gas_out", "mass_flow"),
    ("doublet.esp", "flow"): ("doublet.esp.fluid_in", "volume_flow"),
    ("doublet.esp", "electricity"): ("doublet.esp", "power_in"),
    ("doublet.well", "wellhead_pressure"): ("doublet.well.wellhead_out", "pressure"),
    ("doublet.well", "wellhead_temperature"): ("doublet.well.wellhead_out", "temperature"),
    ("doublet.riser", "wellhead_pressure"): ("doublet.riser.wellhead_out", "pressure"),
    ("doublet.riser", "wellhead_temperature"): ("doublet.riser.wellhead_out", "temperature"),
    ("doublet.injector", "bottomhole_pressure"): ("doublet.injector.bottom_out", "pressure"),
    ("doublet.injector", "bottomhole_temperature"): ("doublet.injector.bottom_out", "temperature"),
    ("injection_pump", "electricity"): ("injection_pump", "power_in"),
    ("doublet.well", "heat_loss"): ("doublet.well", "loss_out"),
    ("doublet.riser", "heat_loss"): ("doublet.riser", "loss_out"),
    ("doublet.injector", "heat_loss"): ("doublet.injector", "loss_out"),
}
"""Columns of the stored reference frames that a port of the module now shows."""


def on_ports(frame):
    """Return a reference ``frame`` with the columns a port shows under their port names."""
    frame = frame.copy()
    frame.columns = pd.MultiIndex.from_tuples(
        [PORT_COLUMNS.get(tuple(column), tuple(column)) for column in frame.columns],
        names=frame.columns.names,
    )
    return frame


def path_frame(results):
    """Return ``results.to_frame()`` with ``(module_path, field)`` MultiIndex columns.

    ``to_frame`` names its columns ``path.field`` (a field of the root plant by its own name);
    this splits each name at its last dot, which fields never contain.
    """
    frame = results.to_frame()
    pairs = [split_path(name) for name in frame.columns]
    if pairs:
        frame.columns = pd.MultiIndex.from_tuples(pairs, names=["module_path", "field"])
    else:
        frame.columns = pd.MultiIndex.from_arrays([[], []], names=["module_path", "field"])
    return frame
