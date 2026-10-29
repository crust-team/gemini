"""Shared test-tier configuration."""

import copy
import warnings
from pathlib import Path

import pandas as pd
import pytest

import gemini as gm
from examples.shared.doublet_heat.plant import DoubletHeatPlant

TIER_MARKERS = {
    "unit": pytest.mark.unit,
    "integration": pytest.mark.integration,
    "e2e": pytest.mark.e2e,
}

ROOT = Path(__file__).parents[1]
DATASETS = {
    "fast": ROOT / "examples/shared/doublet_heat/doublet_2024_15min_month.csv",
    "slow": ROOT / "examples/shared/doublet_heat/doublet_2024_15min.csv",
}


@pytest.fixture(scope="session")
def dataset_name(request):
    """Return the selected committed dataset name."""
    return request.config.getoption("--dataset")


@pytest.fixture(scope="session")
def dataset_path(dataset_name):
    """Return the selected committed dataset path."""
    return DATASETS[dataset_name]


@pytest.fixture(scope="session")
def selected_frame(dataset_path):
    """Load the selected committed frame once for read-only test use."""
    return pd.read_csv(dataset_path, parse_dates=["time"])


@pytest.fixture(scope="session")
def selected_dataset(selected_frame):
    """Build the selected immutable in-memory dataset once."""
    return gm.Dataset.from_frame(selected_frame, time_column="time")


@pytest.fixture(scope="session")
def fast_frame():
    """Load the short-window source once, independent of e2e dataset selection."""
    return pd.read_csv(DATASETS["fast"], parse_dates=["time"])


@pytest.fixture(scope="session")
def fast_dataset(fast_frame):
    """Build the immutable fast dataset once for behaviour tests."""
    return gm.Dataset.from_frame(fast_frame, time_column="time")


@pytest.fixture(scope="session")
def reference_dataset():
    """Load the 96-row June window tied to immutable engine-reference goldens."""
    frame = pd.read_csv(DATASETS["slow"], parse_dates=["time"], nrows=96)
    return gm.Dataset.from_frame(frame, time_column="time")


@pytest.fixture(scope="session")
def shared_plant():
    """Load and validate one read-only shared plant design."""
    with warnings.catch_warnings(record=True) as warnings_seen:
        plant = DoubletHeatPlant.load(ROOT / "examples/shared/doublet_heat/plant.json")
    assert not warnings_seen
    return plant


@pytest.fixture
def fresh_plant(shared_plant):
    """Give mutating tests a cheap isolated copy of the shared plant."""
    return copy.deepcopy(shared_plant)


@pytest.fixture(scope="module")
def module_plant(shared_plant):
    """Give a module-scoped shared workflow one isolated plant copy."""
    return copy.deepcopy(shared_plant)


def pytest_collection_modifyitems(items):
    """Mark every test from its top-level test folder."""
    tests = Path(__file__).parent
    for item in items:
        try:
            tier = item.path.relative_to(tests).parts[0]
        except ValueError:
            continue
        marker = TIER_MARKERS.get(tier)
        if marker is not None:
            item.add_marker(marker)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Fail an unmarked fast-tier call that exceeds the one-second budget."""
    outcome = yield
    report = outcome.get_result()
    markers = {marker.name for marker in item.iter_markers()}
    if (
        report.when == "call"
        and report.passed
        and report.duration > 1.0
        and item.config.option.markexpr == "not e2e and not slow"
        and not hasattr(item.config, "workerinput")
        and not markers.intersection({"e2e", "slow"})
    ):
        report.outcome = "failed"
        report.longrepr = (
            f"Fast-tier test took {report.duration:.2f}s (budget: 1.00s). "
            "Move it to slow or make it faster, see .claude/docs/testing.md."
        )
