"""Optimisation and uncertainty sampling over plant parameters."""

from copy import deepcopy

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from gemini.analysis import kpi
from gemini.analysis.schedule import schedule
from gemini.economics import annualised_cost, co2, lcoc, lcoh, lcts
from gemini.engine.run import simulate
from gemini.errors import GeminiError, ValidationError
from gemini.types.shapes import value
from gemini.utils.jsonable import to_plain
from gemini.utils.strings import close_matches, did_you_mean, join_names, join_path

ECONOMICS = {
    "lcoh": lcoh,
    "lcoc": lcoc,
    "lcts": lcts,
    "annualised_cost": annualised_cost,
    "co2": co2,
}
"""The metrics of ``gm.economics``; the others are those of ``gm.kpi.names()``."""
DISTRIBUTIONS = {
    "normal": ("mean", "std"),
    "uniform": ("lower", "upper"),
    "triangular": ("lower", "mode", "upper"),
}
"""The fields of each distribution, in the order of the method of its name of the generator."""
POPULATION_PER_VARIABLE = 5
"""Candidates of a generation per variable: a small budget still sees several generations."""
SMALLEST_POPULATION = 5
"""The fewest candidates of a generation, which ``differential_evolution`` needs."""
SEED = 0
"""Seed of the search: the same call gives the same trials."""


def _checked_metric(name):
    """Return ``name`` when it is a metric, or raise with the close names."""
    known = [*kpi.names(), *ECONOMICS]
    if name not in known:
        raise ValidationError(
            f"optim: metric = {name!r}; expected one of {join_names(known)}"
            f"{did_you_mean(name, known)}",
            path="metric",
            code="unknown_name",
            suggestions=close_matches(name, known),
        )
    return name


def _metric(plant, results, name, assumptions):
    """Return one metric of a finished run; a value it cannot give is ``None`` with a reason."""
    if name in ECONOMICS:
        return ECONOMICS[name](plant, results, assumptions=assumptions, on_error="record")
    return kpi.compute(plant, results)[name]


def _is_demand(profile):
    """Return whether ``profile`` is a demand to plan, not a plan: it has no plan's ``attrs``."""
    return (
        isinstance(profile, pd.DataFrame)
        and "heating_demand" in profile
        and "outage_days" not in profile.attrs
    )


def _checked_input(profile, rules):
    """Return ``profile`` when a search can run on it, or raise for a missing profile or rules."""
    if profile is None:
        raise ValidationError(
            "optim: profile = None; expected a demand or a plan",
            path="profile",
            code="missing_value",
        )
    if _is_demand(profile) and rules is None:
        raise ValidationError(
            "optim: rules = None; expected the rules of gm.schedule to plan a demand",
            path="rules",
            code="missing_value",
        )
    return profile


def _planned(trial, profile, rules):
    """Return the run input of one trial: a demand is planned on the design of the trial."""
    return schedule(trial, profile, rules) if _is_demand(profile) else profile


def _trial(plant, profile, rules, parameters, names, assumptions):
    """Return ``(metrics, reason)`` of one run of a copy; a run that fails has its reason."""
    trial = deepcopy(plant)
    try:
        for name, number in parameters.items():
            path, _, parameter = name.rpartition(".")
            trial.set_params(path, {parameter: number})
        results = simulate(trial, _planned(trial, profile, rules))
        return {item: _metric(trial, results, item, assumptions) for item in names}, None
    except GeminiError as error:
        return {}, str(error)


def _broken_constraint(metrics, constraints):
    """Return the reason of the first constraint a trial breaks, or ``None``."""
    for limit in constraints:
        name, lower, upper = limit["metric"], limit.get("minimum"), limit.get("maximum")
        number = metrics[name]["value"]
        if number is None:
            return f"{name} has no value: {metrics[name]['reason']}"
        if (lower is not None and number < lower) or (upper is not None and number > upper):
            return f"{name} = {number}; expected {lower} to {upper}"
    return None


def _entry(parameters, metrics, name, reason):
    """Return one line of the history: the parameters and the objective, with a failed reason."""
    metric = metrics.get(name, value(None, "-", reason))
    return {"parameters": parameters, **metric} | ({"reason": reason} if reason else {})


def _checked_variables(plant, variables):
    """Return ``(names, bounds)`` of the variables, or raise for one that does not fit."""
    if not variables:
        raise ValidationError(
            "optim.minimize: variables = []; expected at least one",
            path="variables",
            code="missing_value",
        )
    names = [join_path(item["path"], item["parameter"]) for item in variables]
    for name, item in zip(names, variables):
        plant.get(name)
        if not item["lower"] < item["upper"]:
            raise ValidationError(
                f"optim.minimize: {name}: lower = {item['lower']}, upper = {item['upper']}; "
                "expected lower below upper",
                path=name,
            )
    return names, [(item["lower"], item["upper"]) for item in variables]


def _generations(evaluations, count):
    """Return ``(population, generations after the first)`` that fit the budget."""
    population = max(SMALLEST_POPULATION, POPULATION_PER_VARIABLE * count)
    if evaluations < population:
        raise ValidationError(
            f"optim.minimize: evaluations = {evaluations}; {count} variables need at least "
            f"{population}",
            path="evaluations",
        )
    return population, evaluations // population - 1


def _best(history, sign):
    """Return the best trial without a reason, or ``None`` with the reason there is none."""
    accepted = [item for item in history if "reason" not in item]
    if not accepted:
        return {"parameters": None, **value(None, "-", "every trial failed or broke a constraint")}
    return min(accepted, key=lambda item: sign * item["value"])


def minimize(
    plant,
    profile,
    variables,
    objective,
    constraints=None,
    evaluations=100,
    *,
    rules=None,
    assumptions=None,
):
    """Return the parameter values that minimise a metric of a simulated plant.

    Each trial copies the plant, sets the variables with ``set_params``, plans a demand on that
    design, simulates and reads the objective from ``gm.kpi`` or ``gm.economics``. The search is
    ``scipy.optimize.differential_evolution`` from a Latin hypercube, with a fixed seed: it needs no
    gradient, takes a failed trial as infinitely bad, and its population gives the exact number of
    simulations. The plant itself is not changed.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    profile : Dataset or DataFrame
        The simulation input; ``None`` raises ``missing_value``. A demand frame, with a column
        ``heating_demand``, is planned for each trial with ``gm.schedule`` and ``rules``, so a
        variable that changes the design changes the plan. A plan or any other simulation input (a
        UTC time index and one column per binding) stays fixed over the trials.
    variables : list of dict
        The decision variables, each ``{path, parameter, lower, upper}``: the module path, the
        parameter name and its closed bounds in the parameter's SI unit.
    objective : str
        The metric to minimise, a name of ``gm.kpi.names()`` or of ``lcoh``, ``lcoc``, ``lcts``,
        ``annualised_cost`` or ``co2``; a metric to maximise is given with a leading ``"-"``.
    constraints : list of dict, optional
        Limits on metrics, each ``{metric, minimum, maximum}`` in the unit of the metric, either
        limit optional; a trial that breaks one is rejected.
    evaluations : int
        The largest number of simulations; at least five per variable, and at least five.
    rules : dict, optional
        The rules of ``gm.schedule``; required with a demand, unused with a plan.
    assumptions : Assumptions, optional
        The prices and the discounting the economic metrics need; ``None`` gives the defaults of
        ``Assumptions``, so an economic metric without one of them has a reason, not a value.

    Returns
    -------
    dict
        Plain JSON ``{best, history, evaluations}``: ``best`` is ``{parameters, value, unit}``
        with ``parameters`` as ``{"path.parameter": value}`` in SI, ready for ``set_params``;
        ``history`` lists every trial's parameters and objective, with a ``reason`` for a trial
        that failed or broke a constraint, which is never ``best``; ``evaluations`` is the number
        of simulations. Without an accepted trial, ``best`` has no value and gives a ``reason``.
    """
    name = _checked_metric(objective.removeprefix("-"))
    sign = -1.0 if objective.startswith("-") else 1.0
    constraints = constraints or []
    names = {name, *(_checked_metric(limit["metric"]) for limit in constraints)}
    keys, bounds = _checked_variables(plant, variables)
    population, generations = _generations(evaluations, len(keys))
    history = []
    run_input = _checked_input(profile, rules)

    def evaluated(point):
        parameters = dict(zip(keys, map(float, point)))
        metrics, reason = _trial(plant, run_input, rules, parameters, names, assumptions)
        reason = reason or metrics[name].get("reason") or _broken_constraint(metrics, constraints)
        history.append(_entry(parameters, metrics, name, reason))
        return np.inf if reason else sign * metrics[name]["value"]

    differential_evolution(
        evaluated,
        bounds,
        maxiter=generations,
        popsize=population,
        tol=0,
        polish=False,
        seed=SEED,
    )
    return to_plain({"best": _best(history, sign), "history": history, "evaluations": len(history)})


def _checked_distribution(plant, name, distribution):
    """Refuse a distribution that does not fit: the parameter, the kind or a missing field."""
    plant.get(name)
    kind = distribution.get("kind")
    if kind not in DISTRIBUTIONS:
        raise ValidationError(
            f"optim.sample: {name}: kind = {kind!r}; expected one of {join_names(DISTRIBUTIONS)}",
            path=name,
            code="unknown_name",
            suggestions=close_matches(str(kind), list(DISTRIBUTIONS)),
        )
    missing = set(DISTRIBUTIONS[kind]) - set(distribution)
    if missing:
        raise ValidationError(
            f"optim.sample: {name}: expected {join_names(sorted(missing))} for {kind}",
            path=name,
            code="missing_value",
        )


def _draw(generator, name, distribution):
    """Return one random value of a parameter."""
    kind = distribution["kind"]
    fields = [distribution[field] for field in DISTRIBUTIONS[kind]]
    try:
        return float(getattr(generator, kind)(*fields))
    except ValueError as error:
        raise ValidationError(f"optim.sample: {name}: {error}", path=name) from error


def _spread(samples, name):
    """Return ``{mean, p5, p50, p95, unit}`` of a metric over the samples that give it."""
    metrics = [item["metrics"][name] for item in samples if name in item["metrics"]]
    numbers = [item["value"] for item in metrics if item["value"] is not None]
    unit = metrics[0]["unit"] if metrics else "-"
    if not numbers:
        fields = dict.fromkeys(("mean", "p5", "p50", "p95"))
        return fields | {"unit": unit, "reason": "no sample gives this metric"}
    low, middle, high = np.percentile(numbers, (5, 50, 95))
    return {"mean": np.mean(numbers), "p5": low, "p50": middle, "p95": high, "unit": unit}


def sample(plant, profile, distributions, metrics, count, seed=0, *, rules=None, assumptions=None):
    """Return the spread of metrics when uncertain parameters are drawn at random.

    Each draw copies the plant, sets the drawn values with ``set_params``, plans a demand on that
    design, simulates and reads the metrics. The plant itself is not changed.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    profile : Dataset or DataFrame
        The simulation input, as for ``minimize``: a demand needs ``rules``, a plan does not.
    distributions : dict
        For each uncertain parameter ``"path.parameter"``, its distribution:
        ``{"kind": "normal", "mean", "std"}``, ``{"kind": "uniform", "lower", "upper"}`` or
        ``{"kind": "triangular", "lower", "mode", "upper"}``, in the parameter's SI unit.
    metrics : list of str
        The metrics to record, as the ``objective`` of ``minimize`` without a sign.
    count : int
        The number of random draws, one simulation each.
    seed : int
        Seed of ``numpy.random.default_rng``; the same seed gives the same draws.
    rules : dict, optional
        The rules of ``gm.schedule``, as for ``minimize``.
    assumptions : Assumptions, optional
        The prices and the discounting the economic metrics need, as for ``minimize``.

    Returns
    -------
    dict
        Plain JSON ``{samples, summary}``: ``samples`` lists each draw's ``parameters`` and
        ``metrics``, a value per metric, with a ``reason`` for a draw whose run failed; ``summary``
        gives, for each metric, ``{mean, p5, p50, p95, unit}`` over the draws that give it, each
        ``None`` with a ``reason`` when none does.
    """
    if count < 1:
        raise ValidationError(f"optim.sample: count = {count}; expected at least 1", path="count")
    names = [_checked_metric(name) for name in metrics]
    for name, distribution in distributions.items():
        _checked_distribution(plant, name, distribution)
    generator = np.random.default_rng(seed)
    samples = []
    run_input = _checked_input(profile, rules)
    for _ in range(count):
        drawn = {key: _draw(generator, key, item) for key, item in distributions.items()}
        found, reason = _trial(plant, run_input, rules, drawn, names, assumptions)
        failed = {"reason": reason} if reason else {}
        samples.append({"parameters": drawn, "metrics": found, **failed})
    summary = {name: _spread(samples, name) for name in names}
    return to_plain({"samples": samples, "summary": summary})
