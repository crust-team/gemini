"""The doublet heat replay on arrays equals the replay row by row exactly."""

import copy

import pandas as pd

import gemini as gm
from gemini import backends


def _replay(plant, dataset, backend):
    engine = gm.Engine()
    with backends.settings(backend=backend):
        return engine, engine.replay(plant, dataset)


def test_doublet_heat_replay_is_identical_on_both_backends(shared_plant, fast_frame):
    """Every column, dtype, skip count, error and summary entry is exact over one day."""
    dataset = gm.Dataset.from_frame(fast_frame.iloc[:96], time_column="time")
    engine, traced = _replay(copy.deepcopy(shared_plant), dataset, "numpy")
    _, plain = _replay(copy.deepcopy(shared_plant), dataset, "python")
    pd.testing.assert_frame_equal(traced.to_frame(), plain.to_frame(), check_exact=True)
    assert traced.to_frame().dtypes.tolist() == plain.to_frame().dtypes.tolist()
    assert traced.skip_counts == plain.skip_counts and traced.errors == plain.errors
    pd.testing.assert_frame_equal(
        pd.DataFrame(traced.summary()), pd.DataFrame(plain.summary()), check_exact=True
    )
    assert all(reasons == [] for reasons in engine.graph_breaks.values())
