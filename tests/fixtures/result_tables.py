"""Finished-run results built from given leaf columns, for tests of what reads a run."""

from datetime import datetime, timedelta, timezone

import numpy as np

from gemini.core.engine.chunks import PathColumns, ResultChunk
from gemini.core.engine.results import Results

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_results(columns, step=3600.0, units=None):
    """Return results holding ``columns`` as ``{path: {field: values}}`` at ``step`` seconds.

    ``units`` is ``{path: {field: unit}}`` as the engine records it; every column needs the
    same number of values.
    """
    count = len(next(iter(next(iter(columns.values())).values())))
    times = [START + timedelta(seconds=step * tick) for tick in range(count)]
    tables = {
        path: PathColumns(
            np.ones(count, dtype=bool),
            {field: np.asarray(values, dtype=float) for field, values in fields.items()},
        )
        for path, fields in columns.items()
    }
    results = Results(units)
    results.commit(ResultChunk(times, [step] * count, tables, [{}] * count))
    return results
