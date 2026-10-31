"""Solving a constraint of a plant: the free value at which a target reaches its value.

A constraint names a target path, the value it must reach, a free control or boundary and its
bounds. ``solve`` finds the free value with ``ops.brentq``, running the modules between them
without recording them, and then calls those modules once with it.
"""

from gemini import ops, runtime
from gemini._utils.strings import split_path
from gemini.errors import PhysicsError


def evaluate(function, name, residual, value, unit=""):
    """Return ``residual(value)``; a trial outside a model's domain names the value."""
    try:
        return residual(value)
    except PhysicsError as error:
        raise PhysicsError(
            f"{function}: {name} = {value} {unit}; expected a trial inside the model's domain "
            f"(narrow the bracket): {error}"
        ) from error


def root(function, name, residual, bracket, unit=""):
    """Return the root of ``residual`` in ``bracket`` after checking a sign change at its ends."""
    low, high = bracket
    at_low = evaluate(function, name, residual, low, unit)
    at_high = evaluate(function, name, residual, high, unit)
    if at_low * at_high > 0:
        raise PhysicsError(
            f"{function}: residual = {at_low} at {name} = {low} and {at_high} at {name} = {high}; "
            "expected opposite signs (widen or move the bracket)"
        )
    with runtime.settings(backend=None):
        return ops.brentq(lambda value: evaluate(function, name, residual, value, unit), low, high)


def _bracket(run, bounds):
    """Return the two bounds: a path of a pair, or two numbers or paths."""
    if isinstance(bounds, str):
        return tuple(run.read(bounds))
    return tuple(run.read(bound) if isinstance(bound, str) else bound for bound in bounds)


def solve(run, item):
    """Find the free value of ``item`` and call its modules once with it."""
    constraint = item.constraint
    owner, name = split_path(constraint.by)

    def residual(value):
        run.overrides[owner] = {name: value}
        for step in item.steps:
            run.call(step, trial=True)
        return run.read(constraint.target) - run.read(constraint.value)

    low, high = _bracket(run, constraint.bounds)
    if constraint.at_least and evaluate(run.plant.path, constraint.by, residual, low) >= 0:
        free = low
    else:
        free = root(run.plant.path, constraint.by, residual, (low, high))
    run.overrides[owner] = {name: free}
    for step in item.steps:
        run.call(step)
