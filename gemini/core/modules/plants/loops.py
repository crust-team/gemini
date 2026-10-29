"""Closing a circulation loop inside one plant call by a fixed-point iteration.

A plant that contains a closed circuit (a building loop between a heat exchanger and a consumer)
needs the circulated temperature before its first child can be called. ``close_loop`` finds the
temperature that one pass around the loop maps to itself; the plant evaluates each trial pass
with ``Module.trial_outlets``, which no running call records, and then calls every child exactly
once with the converged state.
"""

import math

from gemini.errors import PhysicsRangeError

TOLERANCE = 1e-9
"""Loop closure tolerance [K]: a pass may change the circulated temperature by at most this."""

MAX_ITERATIONS = 50
"""Most trial passes around a loop before ``close_loop`` gives up."""


def close_loop(update, start, path, lower=-math.inf, upper=math.inf):
    """Return the temperature [K] that one pass around a loop, ``update``, maps to itself.

    The iteration is Wegstein's accelerated successive substitution (Wegstein 1958,
    "Accelerating convergence of iterative processes", Communications of the ACM 1(6), 9-13),
    the classic recycle-convergence method of sequential-modular flowsheet simulators: with
    ``g = update(x)`` and the secant slope ``s`` of ``update`` between the last two iterates,
    ``x_next = q x + (1 - q) g`` with ``q = s / (s - 1)`` for ``s < 1`` and plain substitution
    (``q = 0``) otherwise. It is exact in one accelerated step on a linear piece of ``update``,
    so loops of effectiveness heat exchangers and consumers with capped duties close in a few
    passes. Each iterate is clamped to ``[lower, upper]``, the side on which the loop
    equipment is valid (a heat exchanger needs its hot inlet at least as warm as its cold
    inlet).

    Convergence means ``|update(x) - x| <= TOLERANCE`` (1e-9 K); after ``MAX_ITERATIONS``
    (50) passes without it a ``PhysicsRangeError`` names ``path`` and the last iterate.
    """
    current = min(max(start, lower), upper)
    previous = previous_image = None
    for _ in range(MAX_ITERATIONS):
        image = update(current)
        if abs(image - current) <= TOLERANCE:
            return current
        proposal = image
        if previous is not None and current != previous:
            slope = (image - previous_image) / (current - previous)
            if slope < 1:
                weight = slope / (slope - 1)
                proposal = weight * current + (1 - weight) * image
        previous, previous_image = current, image
        current = min(max(proposal, lower), upper)
    raise PhysicsRangeError(
        f"{path}: loop temperature = {current} K maps to {update(current)} K after "
        f"{MAX_ITERATIONS} passes; expected a change of at most {TOLERANCE} K (the loop did "
        "not converge)"
    )
