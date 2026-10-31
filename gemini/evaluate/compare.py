"""The difference between two runs of a plant."""

from gemini.errors import NotImplementedYet


def compare(plant, problem, results, other):
    """Return how the finished run ``other`` differs from ``results``, metric by metric.

    Parameters
    ----------
    plant : Module
        The plant of both runs.
    problem : Problem
        The problem of both runs.
    results : Results
        The run taken as the reference.
    other : Results
        The run compared with it.

    Raises
    ------
    NotImplementedYet
        Always: the comparison is not built yet.
    """
    raise NotImplementedYet("evaluate.compare")
