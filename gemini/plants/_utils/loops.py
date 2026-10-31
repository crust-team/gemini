"""Closing a loop of a plant: the iteration on its tear streams.

A plant whose connections form a cycle cuts it at one connection, the tear stream, chosen by the
plan. ``close`` finds the stream that one pass around the loop maps to itself. Each pass calls the
modules of the loop without recording them; when the streams have converged every module is
called once with them, so outputs and balances see exactly one call of each.
"""

from gemini._utils.strings import join_path
from gemini.errors import PhysicsError, ValidationError
from gemini.types.flows import STREAM_FIELDS, Stream

TOLERANCE = 1e-9
"""Default convergence of a loop: a pass may change a tear stream field by at most this, in SI."""

MAX_PASSES = 50
"""Default number of passes around a loop before it raises ``PhysicsError``."""


def proposal(current, image, previous, previous_image):
    """Return the next iterate of one field by Wegstein's method.

    Wegstein's accelerated successive substitution (Wegstein 1958, "Accelerating convergence of
    iterative processes", Communications of the ACM 1(6), 9-13) is the classic recycle-convergence
    method of sequential-modular flowsheet simulators: with ``g = image`` and the secant slope
    ``s`` between the last two iterates, ``x_next = q x + (1 - q) g`` with ``q = s / (s - 1)`` for
    ``s < 1`` and plain substitution (``q = 0``) otherwise. It is exact in one accelerated step on
    a linear piece of the pass, so loops of effectiveness heat exchangers and consumers with
    capped duties close in a few passes.
    """
    if previous is None or current == previous:
        return image
    slope = (image - previous_image) / (current - previous)
    if slope >= 1:
        return image
    weight = slope / (slope - 1)
    return weight * current + (1 - weight) * image


class _Field:
    """The iteration on one field of a tear stream."""

    def __init__(self, current, lower=None, upper=None):
        """Start at ``current``, clamped to ``[lower, upper]``; ``None`` is no limit."""
        self.lower, self.upper = lower, upper
        self.current = self._clamped(current)
        self.previous = self.previous_image = None

    def _clamped(self, value):
        if self.lower is not None:
            value = max(value, self.lower)
        return value if self.upper is None else min(value, self.upper)

    def advance(self, image, tolerance):
        """Move to the next iterate unless ``image`` is within ``tolerance``; return if it is."""
        if abs(image - self.current) <= tolerance:
            return True
        next_value = proposal(self.current, image, self.previous, self.previous_image)
        self.previous, self.previous_image = self.current, image
        self.current = self._clamped(next_value)
        return False


class _Tear:
    """The iteration on one tear stream: its mass flow, temperature and pressure."""

    def __init__(self, start, lower, upper):
        """Start from the stream ``start``, the temperature within ``[lower, upper]``."""
        self.fluid = start.fluid
        self.fields = {name: _Field(getattr(start, name)) for name in STREAM_FIELDS}
        self.fields["T"] = _Field(start.T, lower, upper)

    def stream(self):
        """Return the stream of the current iterate."""
        values = {name: field.current for name, field in self.fields.items()}
        return Stream(fluid=self.fluid, **values)

    def advance(self, image, tolerance):
        """Move every field; return whether all of them have converged.

        A stream that stands still carries nothing, so only its flow has to converge.
        """
        settled = [
            field.advance(getattr(image, name), tolerance) for name, field in self.fields.items()
        ]
        if image.m_dot == 0 and self.fields["m_dot"].current == 0:
            return True
        return all(settled)


def _entering(run, step):
    """Return the streams that reach ``step`` from outside its loop."""
    arguments = run.known_arguments(step).values()
    return [value for value in arguments if isinstance(value, Stream)]


def _start(run, loop, tear, lower, upper):
    """Return the first guess of a tear stream: no flow, at what its source module expects.

    A module of the loop may set the pressure, as a circulation pump does, and then the guess does
    not matter. Where none does, the pressure stays the highest that enters the loop, so a pipe in
    it has something to lose. The fluid is that of the water that enters the module of the tear.
    """
    path, port = tear.source
    step = next(item for item in loop.steps if item.path == path)
    module, entering = step.module, _entering(run, step)
    temperature = module._loop_start(port, entering)
    if temperature is None:
        name = join_path(*tear.source)
        raise ValidationError(
            f"{run.plant.path}: tear stream {name} has no first guess; expected a module of the "
            "loop that gives one",
            path=name,
            code="invalid_design",
        )
    pressure = max(
        (stream.p for item in loop.steps for stream in _entering(run, item)), default=0.0
    )
    fluid = entering[0].fluid if entering else module.fluid
    return _Tear(Stream(m_dot=0.0, T=temperature, p=pressure, fluid=fluid), lower, upper)


def _limits(run, loop):
    """Return the tightest temperature limits the modules of a loop set on the tear streams."""
    lower, upper = None, None
    for step in loop.steps:
        low, high = step.module._loop_limits(run.known_arguments(step))
        lower = low if lower is None or (low is not None and low > lower) else lower
        upper = high if upper is None or (high is not None and high < upper) else upper
    return lower, upper


def _not_converged(run, tear, state, passes):
    name = join_path(*tear.source)
    return PhysicsError(
        f"{run.plant.path}: loop temperature at {name} = {state.fields['T'].current} K after "
        f"{passes} passes; expected a change of at most {run.plant.loop_tolerance} K (the loop "
        "did not converge)",
        path=name,
        code="loop_not_converged",
    )


def close(run, loop):
    """Iterate ``loop`` of the running plant until its tear streams converge, then run it once."""
    plant = run.plant
    lower, upper = _limits(run, loop)
    states = [_start(run, loop, tear, lower, upper) for tear in loop.tears]
    for _ in range(plant.loop_passes):
        run.tears = {tear.index: state.stream() for tear, state in zip(loop.tears, states)}
        for step in loop.steps:
            run.call(step, trial=True)
        settled = [
            state.advance(run.outlet(tear.source), plant.loop_tolerance)
            for tear, state in zip(loop.tears, states)
        ]
        if all(settled):
            run.tears = {tear.index: state.stream() for tear, state in zip(loop.tears, states)}
            for step in loop.steps:
                run.call(step)
            return
    raise _not_converged(run, loop.tears[0], states[0], plant.loop_passes)
