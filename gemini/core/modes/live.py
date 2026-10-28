"""Evaluate the latest measurement window using the shared twin evaluator."""

import pandas as pd

from gemini.core.engine.results import Results
from gemini.core.modes.twin import evaluate


def run_latest(plant, config, driver, window):
    """Read a driver's latest window, also accepting the existing CSV driver's loaded frame."""
    if hasattr(driver, "latest"):
        frame = driver.latest(window)
    elif hasattr(driver, "df"):
        frame = driver.df.copy()
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame = frame.sort_index()
        frame = (
            frame.tail(window)
            if isinstance(window, int)
            else frame.loc[frame.index[-1] - pd.Timedelta(window) :]
        )
    else:
        raise TypeError("Live driver must expose latest(window) or a loaded df")
    plant.config = config.model_copy(deep=True)
    plant.skip_counts = {}
    result = Results()
    for at, row in zip(frame.index, frame.to_dict("records")):
        result.append(at, evaluate(plant, row, pd.Timestamp(at)))
    result.skip_counts = {key: dict(value) for key, value in plant.skip_counts.items()}
    return result
