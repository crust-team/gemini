"""The doublet heat replay through the graph equals the tick-by-tick replay exactly."""

import copy

import pandas as pd

import gemini as gm
from gemini import graph


def _replay(plant, dataset, traced):
    engine = gm.Engine()
    with graph.settings(traced=traced):
        return engine, engine.replay(plant, dataset)


def test_doublet_heat_replay_is_identical_with_and_without_the_graph(shared_plant, fast_frame):
    """Every column, dtype, skip count, error and summary entry is exact over one day."""
    dataset = gm.Dataset.from_frame(fast_frame.iloc[:96], time_column="time")
    engine, traced = _replay(copy.deepcopy(shared_plant), dataset, True)
    _, plain = _replay(copy.deepcopy(shared_plant), dataset, False)
    pd.testing.assert_frame_equal(traced.to_frame(), plain.to_frame(), check_exact=True)
    assert traced.to_frame().dtypes.tolist() == plain.to_frame().dtypes.tolist()
    assert traced.skip_counts == plain.skip_counts and traced.errors == plain.errors
    pd.testing.assert_frame_equal(
        pd.DataFrame(traced.summary()), pd.DataFrame(plain.summary()), check_exact=True
    )
    assert engine.batch.reasons == {}
    assert all(any(claims.claimed) for claims in engine.batch.claims.values())
