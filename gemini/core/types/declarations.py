"""Declarations registered by :class:`gemini.core.modules.Module`."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, TypeAdapter, ValidationError

from gemini.core.physics import units
from gemini.core.types.flows import Stream
from gemini.core.types.quantities import Ratio
from gemini.errors import DeclarationError
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


def _adapter(kind, bounds):
    """Return the Pydantic validator of ``kind`` with optional field bounds."""
    return TypeAdapter(Annotated[kind, Field(**bounds)] if bounds else kind)


def _schema_metadata(adapter):
    """Return the JSON schema of ``adapter`` and the quantity, unit and additivity of its value.

    Optional kinds describe the non-null variant, and lists describe their items.
    """
    schema = adapter.json_schema()
    variants = schema.get("anyOf", [schema])
    value_schema = next((value for value in variants if value.get("type") != "null"), schema)
    value_schema = value_schema.get("items", value_schema)
    quantity = value_schema.get("quantity")
    return schema, quantity, value_schema.get("unit"), value_schema.get("additive", False)


class Declaration:
    """Validated metadata attached to one module instance."""

    section = "declaration"

    def __init__(self, kind, *, default=UNSET, description=None, **bounds):
        """Build validation metadata for one declared value."""
        self.kind = kind
        self.default = default
        self.description = description
        self.bounds = dict(bounds)
        self.name = None
        self.owner = None
        self._adapter = _adapter(kind, bounds)
        self.schema, self.quantity, self.unit, self.additive = _schema_metadata(self._adapter)

    @property
    def path(self):
        """Return the declaration's fully qualified module path."""
        if self.owner is None or self.name is None:
            return self.name or "<unbound>"
        return f"{self.owner.path}.{self.name}"

    def bind(self, owner, name):
        """Attach this declaration to a module and local name."""
        self.owner, self.name = owner, name
        return self

    def validate(self, value):
        """Convert public units and validate the resulting SI value."""
        try:
            value = units.value_in_si(value, self.unit, self.path, self.quantity)
            return self._adapter.validate_python(value)
        except (TypeError, ValueError, ValidationError) as exc:
            raise DeclarationError(
                f"{self.path}: invalid {self.section} value {value!r}"
                + (f"; expected {self.unit}" if self.unit else "")
                + f" ({exc})"
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
        description=None,
        **bounds,
    ):
        """Create design data with optional shape, bounds and calibration metadata."""
        super().__init__(kind, default=default, description=description, **bounds)
        self.shape = shape
        self.calibratable = calibratable
        self.value = UNSET
        self._history: list[tuple[datetime | None, Any]] = []
        if default is not UNSET:
            self.value = self.validate(deepcopy(default))
            self._history.append((None, deepcopy(self.value)))

    @property
    def history(self):
        """Project the owner's dated snapshots onto this parameter."""
        if self.owner is None or not getattr(self.owner, "param_history", None):
            return deepcopy(self._history)
        return [
            (snapshot.valid_from, self.validate(snapshot.params[self.name]))
            for snapshot in self.owner.param_history
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
    """Fluid port declaration; ``kind`` must be a ``Stream`` type."""

    def __init__(self, kind=Stream, *, description=None):
        """Declare a fluid port carrying streams of ``kind``."""
        if not isinstance(kind, type) or not issubclass(kind, Stream):
            raise DeclarationError(
                f"{type(self).__name__}: kind = {kind!r}; expected a fluid Stream type"
            )
        super().__init__(kind, description=description)


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
        self._formula_kind_given = True
        self._resolved_formula = None

    @classmethod
    def _from_formula(cls, formula, kind, **kwargs):
        """Declare a formula output; without ``kind`` the target's kind is adopted later."""
        output = cls(kind or Any, **kwargs)
        output.formula = formula
        output._formula_kind_given = kind is not None
        return output

    @classmethod
    def of(cls, target, kind=None, **kwargs):
        """Declare an output copied from one exactly-once descendant call.

        ``target`` is a descendant's output declaration, such as
        ``self.heat_exchanger.duty``, or an outlet field, such as
        ``self.degasser.gas.field("m_dot")``; the output takes the target's kind.
        """
        if isinstance(target, (Output, PortField)):
            kind = target.kind
        return cls._from_formula(("of", target), kind, **kwargs)

    @classmethod
    def total(cls, name, kind=None, **kwargs):
        """Declare the sum of one additive output over descendant leaf calls."""
        output = cls._from_formula(("total", name), kind, **kwargs)
        if kind is not None and not output.additive:
            raise DeclarationError(
                f"Output.total({name!r}): quantity = {output.quantity or kind!r}; "
                "expected an additive quantity"
            )
        return output

    @classmethod
    def ratio(cls, numerator, denominator, kind=None, **kwargs):
        """Declare the ratio of two earlier outputs on the same module."""
        return cls._from_formula(("ratio", numerator, denominator), kind or Ratio | None, **kwargs)

    def infer_kind(self, declaration):
        """Adopt an inferred formula target kind while preserving output metadata."""
        if self._formula_kind_given:
            return
        self.kind = declaration.kind
        self._adapter = _adapter(self.kind, {})
        self.schema, self.quantity, self.unit, self.additive = _schema_metadata(self._adapter)


class Outlet(_StreamPort):
    """Outgoing fluid stream port."""

    section = "outlet"

    def field(self, name):
        """Return a reference to one ``Stream`` field of this outlet for ``Output.of``."""
        if name not in self.kind.model_fields:
            raise DeclarationError(
                f"{self.path}.{name}: unknown stream field; valid: "
                f"{join_names(self.kind.model_fields)}{did_you_mean(name, self.kind.model_fields)}"
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
        return self.port.kind.model_fields[self.name].annotation

    @property
    def path(self):
        """Return the dotted path of the field, for messages."""
        return f"{self.port.path}.{self.name}"
