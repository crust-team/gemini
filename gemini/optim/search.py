"""Optimisation and uncertainty sampling over plant parameters."""

from gemini.errors import NotImplementedYet


def minimize(plant, profile, variables, objective, constraints=None, evaluations=100):
    """Return the parameter values that minimise a metric of a simulated plant.

    Each trial sets the variables with ``plant.set_params`` on a copy, simulates the profile and
    reads the objective from ``gm.kpi`` or ``gm.economics``.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    profile : Dataset or DataFrame
        The simulation input: a UTC time index and one column per binding.
    variables : list of dict
        The decision variables, each ``{path, parameter, lower, upper}``: the module path, the
        parameter name and its closed bounds in the parameter's SI unit.
    objective : str
        The metric to minimise, a name of ``gm.kpi.names()`` or of ``lcoh``, ``lcoc`` or ``co2``;
        a metric to maximise is given with a leading ``"-"``.
    constraints : list of dict, optional
        Limits on metrics, each ``{metric, minimum, maximum}``; a trial that breaks one is
        rejected.
    evaluations : int
        The largest number of simulations.

    Returns
    -------
    dict
        Plain JSON ``{best, history, evaluations}``: ``best`` is ``{parameters, value, unit}``
        with ``parameters`` as ``{"path.parameter": value}``, ready for ``set_params``;
        ``history`` lists every trial's parameters and objective.

    Raises
    ------
    NotImplementedYet
        Always: the search is not built yet.
    """
    raise NotImplementedYet("optim.minimize")


def sample(plant, profile, distributions, metrics, count, seed=0):
    """Return the spread of metrics when uncertain parameters are drawn at random.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    profile : Dataset or DataFrame
        The simulation input, as for ``minimize``.
    distributions : dict
        For each uncertain parameter ``"path.parameter"``, its distribution:
        ``{"kind": "normal", "mean", "std"}``, ``{"kind": "uniform", "lower", "upper"}`` or
        ``{"kind": "triangular", "lower", "mode", "upper"}``, in the parameter's SI unit.
    metrics : list of str
        The metrics to record, as the ``objective`` of ``minimize``.
    count : int
        The number of random draws, one simulation each.
    seed : int
        Seed of the generator; the same seed gives the same draws.

    Returns
    -------
    dict
        Plain JSON ``{samples, summary}``: ``samples`` lists each draw's parameters and metric
        values; ``summary`` gives, for each metric, ``{mean, p5, p50, p95, unit}``.

    Raises
    ------
    NotImplementedYet
        Always: the sampling is not built yet.
    """
    raise NotImplementedYet("optim.sample")
