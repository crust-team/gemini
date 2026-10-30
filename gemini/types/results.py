"""Health and immutable per-call module results."""

from dataclasses import dataclass, field
from functools import partial
from typing import Any

import numpy as np

from gemini import ops
from gemini.errors import PhysicsRangeError, UnitError, UnknownPortError
from gemini.physics import units
from gemini.types.flows import Stream
from gemini.types.ports import Ports
from gemini.utils.mappings import AttributeMapping
from gemini.utils.strings import did_you_mean, join_names, join_path

NOT_ASSESSED = "No diagnostic model or sufficient measurements"
"""Health message of a row that was not assessed, as a module without health reports it."""


@dataclass(slots=True, kw_only=True)
class Health:
    """Comparison of predicted equipment performance with measurements.

    Every field is a scalar for one call or an array over a chunk of ticks (``message`` an array
    of strings). ``score`` is a fraction, one is nominal [-]; ``assessed`` tells that a
    diagnostic model was evaluated; ``alarm`` that a monitoring limit is exceeded; ``metrics``
    maps names to values, finite where assessed and NaN where a row has no metric. Validation
    is ``ops.check``, so it holds for scalars, arrays (the first failing row raises) and traced
    values alike: a score outside ``[0, 1]`` or a non-finite metric of an assessed row raises
    ``PhysicsRangeError``. Plain integers become ``float``.
    """

    assessed: Any = True
    score: Any
    alarm: Any
    message: Any
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Convert plain numbers to ``float`` and check the score and the metrics."""
        self.score = _number(self.score)
        ops.check(
            ops.logical_and(self.score >= 0, self.score <= 1),
            PhysicsRangeError,
            "Health.score: value = {score}; expected a finite fraction in [0, 1]",
            score=self.score,
        )
        self.metrics = {name: _number(value) for name, value in self.metrics.items()}
        for name, value in self.metrics.items():
            ops.check(
                ops.logical_or(ops.logical_not(self.assessed), ops.isfinite(value)),
                PhysicsRangeError,
                "Health.metrics[{name}]: value = {value}; expected a finite number",
                name=name,
                value=value,
            )


def _number(value):
    """Return a Python or NumPy scalar number as ``float``; arrays and traced values pass."""
    return float(value) if isinstance(value, (int, float, np.integer, np.floating)) else value


class Values(AttributeMapping):
    """Read-only attribute and mapping access to named call values."""

    key_error = UnknownPortError
    attribute_error = UnknownPortError

    def __init__(self, values=None, declarations=None):
        """Store immutable-by-interface values and declaration metadata."""
        super().__init__(values)
        object.__setattr__(self, "_declarations", dict(declarations or {}))

    @classmethod
    def _trusted(cls, values, declarations):
        """Return values over ``values``, a dict this call owns, sharing ``declarations``."""
        mapping = object.__new__(cls)
        object.__setattr__(mapping, "_values", values)
        object.__setattr__(mapping, "_declarations", declarations)
        return mapping

    def _unknown(self, name):
        """Name the unknown value, the valid names and the closest match."""
        return (
            f"unknown value {name!r}; valid names: {join_names(self._values)}"
            f"{did_you_mean(name, self._values)}"
        )

    def mapped(self, function):
        """Return values with ``function`` applied to each, sharing the declarations."""
        return Values._trusted(
            {name: function(value) for name, value in self._values.items()}, self._declarations
        )

    def row(self, index):
        """Return the values of one row of a chunk as plain Python values.

        A declared ``X | None`` output that is NaN reads back as ``None``, like a direct call.
        """
        values = {}
        for name, value in self._values.items():
            plain = row_value(value, index)
            values[name] = None if self.accepts_none(name) and plain != plain else plain
        return Values._trusted(values, self._declarations)

    def accepts_none(self, name):
        """Return whether output ``name`` is declared ``X | None``."""
        declaration = self._declarations.get(name)
        return declaration is not None and declaration.accepts_none()

    def get(self, name, default=None, *, unit=None):
        """Return one value, optionally converted from its declared SI unit.

        Differences such as a temperature difference convert by scale only.
        """
        if name not in self._values:
            return default
        value = self._values[name]
        if unit is None:
            return value
        declaration = self._declarations.get(name)
        if declaration is None or declaration.unit is None:
            raise UnitError(f"{name}: unit = None; expected a declared physical unit")
        return units.convert(value, declaration.unit, unit, declaration.quantity)


def row_value(value, index):
    """Return row ``index`` of a column as a plain Python value; a non-column passes unchanged.

    A NumPy array or a list is a column over the rows of a chunk; a NumPy scalar becomes the
    matching Python type, so a row of an array result equals a direct call's value.
    """
    if isinstance(value, np.ndarray) and value.ndim:
        return value[index].tolist()
    if isinstance(value, list):
        return value[index]
    return value.item() if isinstance(value, np.generic) else value


@dataclass(frozen=True)
class ModuleResult:
    """Computed outputs, outgoing flows and the evaluation audit data of one call.

    One class on every backend: the values are scalars for a direct call, arrays over a chunk
    of ticks for an evaluated graph, or traced values inside a trace. ``outputs`` and ``outlets``
    are read-only mappings. ``inputs`` and ``children`` are plain dictionaries captured at
    evaluation time; treat them as read-only. ``leaves()`` treats a result without called
    children as a leaf. ``mapped(function)`` maps the whole tree to new values, and
    ``row(index)`` takes one row of a tree of array results.
    """

    outputs: Values
    outlets: Ports
    inlets: Ports = field(default_factory=Ports)
    inputs: dict[str, Any] = field(default_factory=dict)
    children: dict[str, "ModuleResult"] = field(default_factory=dict)
    call_records: tuple[tuple[str, "ModuleResult"], ...] = field(default_factory=tuple, repr=False)
    is_leaf: bool = True

    @classmethod
    def of(cls, module, outputs, outlets, inlets, inputs, records):
        """Return the result of a call of ``module``: the one way a call's result is built.

        ``records`` are the ``(relative path, result)`` pairs of the child calls it made.
        """
        return cls(
            outputs=Values(outputs, module._outputs),
            outlets=outlets,
            inlets=inlets,
            inputs=dict(inputs),
            children=dict(records),
            call_records=tuple(records),
            is_leaf=module.is_leaf,
        )

    def leaves(self, prefix=""):
        """Flatten only descendant leaf results, with relative module paths."""
        if not self.children:
            return {prefix: self}
        result = {}
        for name, child in self.children.items():
            result.update(child.leaves(join_path(prefix, name)))
        return result

    def mapped(self, function):
        """Return the tree with ``function`` applied to every value, keeping its structure.

        The values are the outputs, the ``m_dot``, ``T`` and ``p`` of every inlet and outlet
        stream and the inputs, of this result and of all descendants; fluids and a child shared
        by ``children`` and ``call_records`` stay as they are. The runner maps the proxies of a
        trace to arrays with it.
        """
        return self._mapped(function, partial(Values.mapped, function=function), {})

    def row(self, index):
        """Return the tree for row ``index`` of a tree of array results, as plain Python values."""
        return self._mapped(partial(row_value, index=index), partial(Values.row, index=index), {})

    def _mapped(self, function, map_outputs, done):
        """Map this result and, once each, its descendants."""
        if id(self) in done:
            return done[id(self)]
        records = tuple(
            (name, child._mapped(function, map_outputs, done)) for name, child in self.call_records
        )
        children = {
            name: child._mapped(function, map_outputs, done)
            for name, child in self.children.items()
        }
        result = ModuleResult(
            outputs=map_outputs(self.outputs),
            outlets=_mapped_ports(self.outlets, function),
            inlets=_mapped_ports(self.inlets, function),
            inputs={name: _mapped_input(value, function) for name, value in self.inputs.items()},
            children=children,
            call_records=records,
            is_leaf=self.is_leaf,
        )
        done[id(self)] = result
        return result


def _mapped_ports(ports, function):
    """Return ports whose streams carry ``function`` of their ``m_dot``, ``T`` and ``p``."""
    streams = {
        name: Stream._trusted(
            function(stream.m_dot), function(stream.T), function(stream.p), stream.fluid
        )
        for name, stream in ports.items()
    }
    return Ports._trusted(streams, ports._path)


def _mapped_input(value, function):
    """Return one input mapped; a stream input maps like a port stream."""
    if isinstance(value, Stream):
        return Stream._trusted(
            function(value.m_dot), function(value.T), function(value.p), value.fluid
        )
    return function(value)
