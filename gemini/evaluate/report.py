"""One report of a finished run."""

from gemini.errors import NotImplementedYet


def report(plant, problem, results):
    """Return the totals, checks and costs of a finished run as one plain document.

    Parameters
    ----------
    plant : Module
        The plant of the run.
    problem : Problem
        The problem of the run.
    results : Results
        A finished run.

    Raises
    ------
    NotImplementedYet
        Always: the report is not built yet.
    """
    raise NotImplementedYet("evaluate.report")
