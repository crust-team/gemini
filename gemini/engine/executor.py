"""Executors: the ways the engine evaluates a module over the rows of a chunk.

An ``Executor`` has two steps. ``prepare(module, streams, inputs, stepped)`` takes the inlet
streams and the controls and boundaries (dotted path to column) of the selected rows and returns
what ``evaluate`` needs; an exception of this step is the error of every selected row.
``evaluate(prepared, rows, context)`` returns an ``Evaluation`` (``gemini.engine.evaluation``);
``context`` holds ``dt`` (the seconds of every row) and ``states`` (the state tree of a stepped
call). The eager executor of ``gemini.engine.eager`` is always there; a package that evaluates
better registers a factory under the name ``"compiled"`` with ``register_executor``, and an
engine built with ``compile=True`` uses it.
"""

from gemini._utils.strings import did_you_mean, join_names
from gemini.errors import ValidationError

_FACTORIES = {}
COMPILED = "compiled"
EAGER = "eager"


class Executor:
    """Base of the executors: subclasses define ``prepare`` and ``evaluate``."""

    def prepare(self, module, streams, inputs, stepped):
        """Return what ``evaluate`` needs for ``module`` on the given inlets and inputs."""
        raise NotImplementedError(f"{type(self).__name__} does not prepare")

    def evaluate(self, prepared, rows, context):
        """Return the ``Evaluation`` of the prepared call over ``rows`` rows."""
        raise NotImplementedError(f"{type(self).__name__} does not evaluate")


def register_executor(name, factory):
    """Make ``factory(plant)``, which returns an ``Executor``, selectable by ``name``."""
    _FACTORIES[name] = factory
    return factory


def executor_for(plant, compile=True):
    """Return the executor for ``plant``: the compiled one when asked and registered, else eager."""
    name = COMPILED if compile and COMPILED in _FACTORIES else EAGER
    if name not in _FACTORIES:
        raise ValidationError(
            f"executors: executor = {name!r}; expected one of {join_names(_FACTORIES)}"
            f"{did_you_mean(name, _FACTORIES)}",
            code="unknown_name",
        )
    return _FACTORIES[name](plant)
