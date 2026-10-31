"""Spread of metrics when uncertain parameters are drawn at random."""

import numpy as np

from gemini._utils.jsonable import to_plain
from gemini._utils.strings import close_matches, join_names
from gemini.errors import ValidationError
from gemini.optim._utils.trial import checked_metric, require_input, run_trial

DISTRIBUTIONS = {
    "normal": ("mean", "std"),
    "uniform": ("lower", "upper"),
    "triangular": ("lower", "mode", "upper"),
}
"""The fields of each distribution, in the order of the method of its name of the generator."""


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


def sample(plant, problem, distributions, metrics, count, seed=0, *, plan=None):
    """Return the spread of metrics when uncertain parameters are drawn at random.

    Each draw copies the plant, sets the drawn values with ``set_params``, simulates it on the
    problem (``gm.simulate`` plans the demand on that design) and reads the metrics. The plant
    itself is not changed.

    Parameters
    ----------
    plant : Module
        A plant with parameter values.
    problem : Problem or None
        What the plant is asked to do, as for ``minimize``.
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
    plan : DataFrame, optional
        The run input held fixed over the draws, as for ``minimize``.

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
    names = [checked_metric(name, problem) for name in metrics]
    for name, distribution in distributions.items():
        _checked_distribution(plant, name, distribution)
    generator = np.random.default_rng(seed)
    samples = []
    require_input(problem, plan)
    for _ in range(count):
        drawn = {key: _draw(generator, key, item) for key, item in distributions.items()}
        found, reason = run_trial(plant, problem, plan, drawn, names)
        failed = {"reason": reason} if reason else {}
        samples.append({"parameters": drawn, "metrics": found, **failed})
    summary = {name: _spread(samples, name) for name in names}
    return to_plain({"samples": samples, "summary": summary})
