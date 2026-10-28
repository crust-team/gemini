"""Shared test-tier configuration."""

from pathlib import Path

import pytest

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


def pytest_addoption(parser):
    """Add the committed real-data selection used by end-to-end tests."""
    parser.addoption(
        "--dataset",
        choices=sorted(DATASETS),
        default="fast",
        help="committed e2e dataset: fast July month (default) or slow full year",
    )


@pytest.fixture(scope="session")
def dataset_name(request):
    """Return the selected committed dataset name."""
    return request.config.getoption("--dataset")


@pytest.fixture(scope="session")
def dataset_path(dataset_name):
    """Return the selected committed dataset path."""
    return DATASETS[dataset_name]


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
