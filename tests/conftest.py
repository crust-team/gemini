"""Shared test-tier configuration."""

from pathlib import Path

import pytest


TIER_MARKERS = {
    "unit": pytest.mark.unit,
    "integration": pytest.mark.integration,
    "e2e": pytest.mark.e2e,
}


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
