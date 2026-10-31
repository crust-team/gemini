"""One trial of a search: a copy of the plant with drawn values, run and read."""

from copy import deepcopy

from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.errors import GeminiError, ValidationError
from gemini.evaluate import annualised_cost, co2, lcoc, lcoh, lcts, totals
from gemini.evaluate.totals import KPI_NAMES
from gemini.run.simulate import simulate

ECONOMICS = {
    "lcoh": lcoh,
    "lcoc": lcoc,
    "lcts": lcts,
    "annualised_cost": annualised_cost,
    "co2": co2,
}
"""The economic metrics of ``gm.evaluate``; the others are the KPIs of ``gm.evaluate.totals``."""


def checked_metric(name, problem):
    """Return ``name`` when it is a metric the call can read, or raise with the close names."""
    known = [*KPI_NAMES, *ECONOMICS]
    if name not in known:
        raise ValidationError(
            f"optim: metric = {name!r}; expected one of {join_names(known)}"
            f"{did_you_mean(name, known)}",
            path="metric",
            code="unknown_name",
            suggestions=close_matches(name, known),
        )
    if name in ECONOMICS and problem is None:
        raise ValidationError(
            f"optim: metric = {name!r} needs the assumptions of a problem; problem = None",
            path="problem",
            code="missing_value",
        )
    return name


def require_input(problem, plan):
    """Raise ``missing_value`` unless a search has a problem or a plan to run."""
    if problem is None and plan is None:
        raise ValidationError(
            "optim: problem = None and plan = None; expected a problem or a plan",
            path="problem",
            code="missing_value",
        )


def _metric(plant, problem, results, name):
    """Return one metric of a finished run; a value it cannot give is ``None`` with a reason."""
    if name in ECONOMICS:
        return ECONOMICS[name](plant, problem, results, on_error="record")
    return totals(plant, problem, results)[name]


def run_trial(plant, problem, plan, parameters, names):
    """Return ``(metrics, reason)`` of one run of a copy; a run that fails has its reason."""
    trial = deepcopy(plant)
    try:
        for name, number in parameters.items():
            path, _, parameter = name.rpartition(".")
            trial.set_params(path, {parameter: number})
        results = simulate(trial, problem, plan=plan)
        return {item: _metric(trial, problem, results, item) for item in names}, None
    except GeminiError as error:
        return {}, str(error)
