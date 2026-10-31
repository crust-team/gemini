"""The capacity each unit of a plant needed in a run."""

from gemini.errors import NotImplementedYet


def capacities(plant, problem, results):
    """Return the peak load of each unit of a plant over a run, against its rated capacity.

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
        Always: the capacities are not built yet.
    """
    raise NotImplementedYet("evaluate.capacities")
