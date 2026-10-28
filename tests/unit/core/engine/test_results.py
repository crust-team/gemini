"""Result collection tests."""

from gemini.core.engine.results import Results


def test_empty_results_summary():
    """An empty finite run has an empty summary."""
    assert Results().summary().empty
