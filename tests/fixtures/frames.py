"""Read a results table by module path and field, as tests compare it with reference tables."""

import pandas as pd

from gemini.utils.strings import split_path


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
