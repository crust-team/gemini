"""Declarations registered by :class:`gemini.modules.Module`."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import datetime
from functools import partial
from typing import Annotated, Any

import numpy as np
from pydantic import Field, TypeAdapter, ValidationError

from gemini import ops
from gemini.errors import DeclarationError, UnitError
from gemini.physics import units
from gemini.types import streams
from gemini.types.flows import Stream
from gemini.types.quantities import Ratio
from gemini.utils.strings import did_you_mean, join_names


class _Unset:
    """Type of the ``UNSET`` sentinel; copying or pickling returns the same object."""

    def __repr__(self):
        """Return ``UNSET``."""
        return "UNSET"

    def __copy__(self):
        """Return the sentinel itself."""
        return self

    def __deepcopy__(self, memo):
        """Return the sentinel itself."""
        return self

    def __reduce__(self):
        """Pickle as a reference to the module-level ``UNSET``."""
        return "UNSET"


UNSET = _Unset()


_NUMPY_KINDS = {float: np.float64, bool: np.bool_}

_MISS = object()
"""Result of a quick check that cannot decide; the full validation then runs."""

_PLAIN_KEYS = {
    "type",
    "minimum",
    "exclusiveMinimum",
    "maximum",
    "exclusiveMaximum",
    "quantity",
    "unit",
    "additive",
}


def _exact(kind, optional, value):
    """Return ``value`` when it is exactly a ``kind`` (or ``None`` if optional), else ``_MISS``.

    An ``np.float64`` or ``np.bool_`` of the eager scope converts to its Python kind.
    """
    if type(value) is kind or (value is None and optional):
        return value
    if type(value) is _NUMPY_KINDS.get(kind):
        return kind(value)
    return _MISS


def _bounded_float(ge, gt, le, lt, optional, value):
    """Return ``value`` when it is a ``float`` within every bound (NaN never is), else ``_MISS``."""
    if type(value) is np.float64:
        value = float(value)
    if type(value) is not float:
        return None if value is None and optional else _MISS
    if (
        (ge is None or value >= ge)
        and (gt is None or value > gt)
        and (le is None or value <= le)
        and (lt is None or value < lt)
    ):
        return value
    return _MISS


def _miss(value):
    return _MISS


def _quick_check(schema, limits):
    """Return the cheap check of the common case of a declared kind, from its JSON schema.

    Only a plain number, flag or text (or one of them or ``None``) has one: it accepts the value
    exactly as validation would, unchanged, and returns ``_MISS`` for everything else. The
    check is a ``functools.partial`` of module functions, so a declaration still copies and
    pickles.
    """
    variants = schema.get("anyOf", [schema])
    values = [variant for variant in variants if variant.get("type") != "null"]
    if len(values) != 1 or set(values[0]) - _PLAIN_KEYS:
        return _miss
    optional = len(values) < len(variants)
    kind = values[0].get("type")
    if kind == "number" and limits:
        bounds = (limits.get(key) for key in ("ge", "gt", "le", "lt"))
        return partial(_bounded_float, *bounds, optional)
    exact = {"number": float, "boolean": bool, "string": str}.get(kind)
    return partial(_exact, exact, optional) if exact else _miss


_BOUND_FAILURES = {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}


def _failure_code(cause):
    """Return the ``gm.errors.CODES`` entry of a failed validation: unit, bound or other value."""
    if isinstance(cause, UnitError):
        return "invalid_unit"
    if isinstance(cause, ValidationError) and any(
        item["type"] in _BOUND_FAILURES for item in cause.errors()
    ):
        return "out_of_bounds"
    return "invalid_value"


def _adapter(kind, bounds):
    """Return the Pydantic validator of ``kind`` with optional field bounds."""
    return TypeAdapter(Annotated[kind, Field(**bounds)] if bounds else kind)


_LIMIT_KEYS = {"minimum": "ge", "exclusiveMinimum": "gt", "maximum": "le", "exclusiveMaximum": "lt"}


def _limits(schema):
    """Return the ``ge``/``gt``/``le``/``lt`` bounds of the value (or list item) in ``schema``."""
    value_schema = _value_schema(schema)
    return {key: value_schema[name] for name, key in _LIMIT_KEYS.items() if name in value_schema}


def _value_schema(schema):
    """Return the schema of the non-null variant of ``schema``, or of its list items."""
    variants = schema.get("anyOf", [schema])
    value_schema = next((value for value in variants if value.get("type") != "null"), schema)
    return value_schema.get("items", value_schema)


def _schema_metadata(adapter):
    """Return the JSON schema of ``adapter`` and the quantity, unit and additivity of its value.

    Optional kinds describe the non-null variant, and lists describe their items.
    """
    schema = adapter.json_schema()
    value_schema = _value_schema(schema)
    quantity = value_schema.get("quantity")
    return schema, quantity, value_schema.get("unit"), value_schema.get("additive", False)


_IMMUTABLE = (float, int, bool, str, type(None))


class Declaration:
    """Validated metadata attached to one module instance."""

    section = "declaration"
    _validated_default = _MISS

    def __init__(self, kind, *, default=UNSET, description=None, **bounds):
        """Build validation metadata for one declared value."""
        self.kind = kind
        self.default = default
        self.description = description
        self.bounds = dict(bounds)
        self.name = None
        self.owner = None
        self._adapter = _adapter(kind, bounds)
        self._limits = None
        self.schema, self.quantity, self.unit, self.additive = _schema_metadata(self._adapter)
        self._quick = _quick_check(self.schema, self.limits())

    @property
    def path(self):
        """Return the declaration's fully qualified module path."""
        if self.owner is None or self.name is None:
            return self.name or "<unbound>"
        return f"{self.owner.path}.{self.name}"

    def limits(self):
        """Return the numeric bounds the value must satisfy, as ``ge``/``gt``/``le``/``lt``.

        They are read once from the quantity metadata and the declared ``bounds`` (both are in the
        schema, the stricter wins) and apply to each item of a list. A kind without bounds, such
        as a flag or a text, gives an empty mapping.
        """
        if self._limits is None:
            self._limits = _limits(self.schema)
        return self._limits

    def value_type(self):
        """Return the JSON type of the value (of each list item): ``number``, ``integer``, ...

        ``None`` for a kind without a schema, such as ``Any``.
        """
        return _value_schema(self.schema).get("type")

    def accepts_none(self):
        """Return whether the declared kind is ``X | None``."""
        return any(variant.get("type") == "null" for variant in self.schema.get("anyOf", ()))

    def bind(self, owner, name):
        """Attach this declaration to a module and local name."""
        self.owner, self.name = owner, name
        return self

    def default_value(self):
        """Return the validated default as a fresh value, validating it only the first time."""
        if self._validated_default is _MISS:
            self._validated_default = self.validate(deepcopy(self.default))
        if type(self._validated_default) in _IMMUTABLE:
            return self._validated_default
        return deepcopy(self._validated_default)

    def validate(self, value):
        """Convert public units and validate the resulting SI value.

        A plain value of the declared kind inside its bounds (an exact ``float``, ``bool`` or
        ``str``, or ``None`` for an optional kind) returns unchanged without units or Pydantic;
        any other value, and every failure, takes the full path below. An ``np.float64`` or
        ``np.bool_`` converts to ``float`` or ``bool`` first, and a ``Failed`` raises its error.
        """
        accepted = self._quick(value)
        if accepted is not _MISS:
            return accepted
        value = ops.scope.plain(value)
        try:
            value = units.value_in_si(value, self.unit, self.path, self.quantity)
            return self._adapter.validate_python(value)
        except (TypeError, ValueError, ValidationError) as exc:
            raise DeclarationError(
                f"{self.path}: invalid {self.section} value {value!r}"
                + (f"; expected {self.unit}" if self.unit else "")
                + f" ({exc})",
                code=_failure_code(exc),
            ) from exc


class Parameter(Declaration):
    """Design data fixed during a run, with optional dated values."""

    section = "parameter"

    def __init__(
        self,
        kind,
        *,
        default=UNSET,
        shape=None,
        calibratable=False,
        structural=False,
        description=None,
        **bounds,
    ):
        """Create design data with optional shape, bounds and calibration metadata.

        A ``structural`` parameter decides the shape of the computation (a loop count, a value
        that changes a ``Fluid``): a trace reads it as a plain value and its value is a guard of
        the graph cache, never a graph input.
        """
        super().__init__(kind, default=default, description=description, **bounds)
        self.shape = shape
        self.calibratable = calibratable
        self.structural = structural
        self.value = UNSET
        self._history: list[tuple[datetime | None, Any]] = []
        if default is not UNSET:
            self.value = self.validate(deepcopy(default))
            self._history.append((None, deepcopy(self.value)))

    @property
    def history(self):
        """Project the owner's dated snapshots onto this parameter."""
        if self.owner is None or not getattr(self.owner, "_param_history", None):
            return deepcopy(self._history)
        return [
            (snapshot.valid_from, self.validate(snapshot.params[self.name]))
            for snapshot in self.owner._param_history
            if self.name in snapshot.params
        ]

    @property
    def initialized(self):
        """Whether the parameter currently contains a value."""
        return self.value is not UNSET

    def validate(self, value):
        """Validate the value and its optional outer shape."""
        value = super().validate(value)
        if self.shape is not None and value is not None:
            actual = (len(value),) if hasattr(value, "__len__") else ()
            if actual != self.shape:
                raise DeclarationError(f"{self.path}: shape = {actual}; expected {self.shape}")
        return value

    def set(self, value, *, explicit=True):
        """Validate and store a current parameter value."""
        self.value = self.validate(value)
        if explicit and self.owner is not None:
            self.owner._param_overrides[self.name] = deepcopy(self.value)
        return self.value


class _StreamPort(Declaration):
    """Fluid port declaration; ``kind`` must be a ``Stream`` type.

    A port has no JSON schema, quantity or unit: ``schema`` is empty, ``quantity`` and ``unit``
    are ``None`` and ``additive`` is false. Stream dataclasses do not go through Pydantic.
    ``stream`` is the stream type of the port, one of ``streams.NAMES``, or ``None`` for a port
    that takes whatever flows through it (a pipe, a valve, either side of a heat exchanger).
    """

    def __init__(self, kind=Stream, *, stream=None, description=None):
        """Declare a fluid port carrying streams of ``kind`` and stream type ``stream``."""
        if stream is not None and stream not in streams.NAMES:
            raise DeclarationError(
                f"{type(self).__name__}: stream = {stream!r}; expected one of "
                f"{join_names(streams.NAMES)}{did_you_mean(stream, streams.NAMES)}"
            )
        if not isinstance(kind, type) or not issubclass(kind, Stream):
            raise DeclarationError(
                f"{type(self).__name__}: kind = {kind!r}; expected a fluid Stream type"
            )
        self.kind = kind
        self.stream = stream
        self.default = UNSET
        self.description = description
        self.bounds = {}
        self.name = None
        self.owner = None
        self._limits = None
        self.schema, self.quantity, self.unit, self.additive = {}, None, None, False

    def validate(self, value):
        """Return a stream of ``kind``: an instance passes, a mapping of its fields builds one."""
        if isinstance(value, self.kind):
            return value
        if isinstance(value, Mapping):
            return self.kind(**value)
        raise DeclarationError(
            f"{self.path}: invalid {self.section} value {value!r}; expected a {self.kind.__name__}"
        )


class Inlet(_StreamPort):
    """Incoming flow port."""

    section = "inlet"


class Control(Declaration):
    """Operating command that an optimiser or agent may change."""

    section = "control"


class Boundary(Declaration):
    """External operating condition that the system cannot set."""

    section = "boundary"


class State(Declaration):
    """Value a stateful module carries from one time step to the next.

    ``default`` is the initial state. ``Module.step`` supplies the value at the start of a step
    and ``_advance_states`` returns the value at its end; a plain call uses the initial state.
    """

    section = "state"

    def __init__(self, kind, *, default, description=None, **bounds):
        """Declare a carried value with its initial state."""
        super().__init__(kind, default=default, description=description, **bounds)
        self.validate(deepcopy(default))


class Output(Declaration):
    """Computed value recorded for one call."""

    section = "output"

    def __init__(self, kind, *, soft_sensor=False, description=None):
        """Declare a computed value and its recording semantics."""
        super().__init__(kind, description=description)
        self.soft_sensor = soft_sensor
        self.formula = None
        self._resolved_formula = None

    @classmethod
    def of(cls, target, **kwargs):
        """Declare an output copied from one exactly-once descendant call.

        ``target`` is a descendant's output declaration, such as ``self.heat_exchanger.duty``,
        or an outlet field, such as ``self.degasser.gas.field("m_dot")``; the output takes the
        target's kind. The owning module checks the reference when the output is assigned.
        """
        output = cls(getattr(target, "kind", Any), **kwargs)
        output.formula = ("of", target)
        return output

    @classmethod
    def ratio(cls, numerator, denominator, **kwargs):
        """Declare the ratio of two earlier outputs of the same module, given as declarations."""
        output = cls(Ratio | None, **kwargs)
        output.formula = ("ratio", numerator, denominator)
        return output


class Outlet(_StreamPort):
    """Outgoing fluid stream port."""

    section = "outlet"

    def field(self, name):
        """Return a reference to one ``Stream`` field of this outlet for ``Output.of``."""
        names = [field.name for field in fields(self.kind)]
        if name not in names:
            raise DeclarationError(
                f"{self.path}.{name}: unknown stream field; valid: "
                f"{join_names(names)}{did_you_mean(name, names)}"
            )
        return PortField(self, name)


@dataclass(frozen=True, eq=False)
class PortField:
    """One ``Stream`` field of an outlet declaration, the target of an ``Output.of`` formula."""

    port: Outlet
    name: str

    @property
    def kind(self):
        """Return the annotated kind of the stream field."""
        return next(field.type for field in fields(self.port.kind) if field.name == self.name)

    @property
    def path(self):
        """Return the dotted path of the field, for messages."""
        return f"{self.port.path}.{self.name}"
