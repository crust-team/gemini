"""PyTorch-style declarations registered by :class:`gemini.modules.Module`."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, TypeAdapter, ValidationError

from gemini.core.physics import units
from gemini.core.types.flows import Stream


class _Unset:
    def __repr__(self):
        return "UNSET"


UNSET = _Unset()


def _adapter(kind, bounds):
    return TypeAdapter(Annotated[kind, Field(**bounds)] if bounds else kind)


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
        schema = self._adapter.json_schema()
        variants = schema.get("anyOf", [schema])
        value_schema = next((value for value in variants if value.get("type") != "null"), schema)
        value_schema = value_schema.get("items", value_schema)
        self.quantity = value_schema.get("quantity")
        self.unit = value_schema.get("unit")
        self.schema = schema

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
            value = units.value_in_si(value, self.unit, self.path)
            return self._adapter.validate_python(value)
        except (TypeError, ValueError, ValidationError) as exc:
            raise TypeError(
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
                raise TypeError(f"{self.path}: expected shape {self.shape}, got {actual}")
        return value

    def set(self, value, *, explicit=True):
        """Validate and store a current parameter value."""
        self.value = self.validate(value)
        if explicit and self.owner is not None:
            self.owner._param_overrides[self.name] = deepcopy(self.value)
        return self.value


class Inlet(Declaration):
    """Incoming flow port."""

    section = "inlet"

    def __init__(self, kind=Stream, *, description=None):
        """Declare an incoming flow of the requested kind."""
        super().__init__(kind, description=description)


class Control(Declaration):
    """Operating command that an optimiser or agent may change."""

    section = "control"


class Boundary(Declaration):
    """External operating condition that the system cannot set."""

    section = "boundary"


class Output(Declaration):
    """Computed value recorded for one call."""

    section = "output"

    def __init__(self, kind, *, soft_sensor=False, optional=False, description=None):
        """Declare a computed value and its recording semantics."""
        super().__init__(kind, description=description)
        self.soft_sensor = soft_sensor
        self.optional = optional


class Outlet(Declaration):
    """Outgoing fluid or energy flow port."""

    section = "outlet"

    def __init__(self, kind=Stream, *, description=None):
        """Declare an outgoing flow of the requested kind."""
        super().__init__(kind, description=description)


@dataclass(frozen=True)
class Quantity:
    """A scalar and unit accepted at public API boundaries."""

    value: float
    unit: str
