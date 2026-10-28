"""Validated equipment contract and monitoring health shared by all components."""

import inspect
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.base.stream import Stream
from gemini.core.physics import fluid


class Health(BaseModel):
    """Comparison of predicted equipment performance with measurements."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    score: float = Field(..., ge=0, le=1, description="Condition score, one is nominal [-]")
    alarm: bool = Field(..., description="Whether a monitoring limit is exceeded [-]")
    message: str = Field(..., description="Explanation of the condition [-]")
    metrics: dict[str, float] = Field(
        default_factory=dict, description="Named diagnostic metrics [-]"
    )


class Component(ABC):
    """Base class for every plant component, with validated compute and port contracts."""

    name: ClassVar[str]
    category: ClassVar[str]
    description: ClassVar[str]
    Params: ClassVar[type[BaseModel]]
    Inputs: ClassVar[type[BaseModel]]
    Outputs: ClassVar[type[BaseModel]]
    inlets: ClassVar[tuple[str, ...]] = ()
    outlets: ClassVar[tuple[str, ...]] = ()
    soft_sensors: ClassVar[tuple[str, ...]] = ()
    calibratable: ClassVar[tuple[str, ...]] = ()
    stateful: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs):
        """Check concrete metadata and wrap compute so direct calls validate the contract."""
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        for key in ("name", "category", "description", "Params", "Inputs", "Outputs"):
            if not hasattr(cls, key):
                raise TypeError(f"{cls.__name__} must define {key}")
        for key in ("Params", "Inputs", "Outputs"):
            if not issubclass(getattr(cls, key), BaseModel):
                raise TypeError(f"{cls.__name__}.{key} must be a Pydantic model")
        for names, model in [(cls.soft_sensors, cls.Outputs), (cls.calibratable, cls.Params)]:
            unknown = set(names) - model.model_fields.keys()
            if unknown:
                raise TypeError(f"{cls.name}: unknown schema fields {sorted(unknown)}")
        method = cls.__dict__.get("compute")
        if method is not None:

            @wraps(method)
            def checked(self, inputs, streams_in):
                inputs = self.Inputs.model_validate(inputs)
                self._check_ports(streams_in, self.inlets, "inlet")
                outputs, streams_out = method(self, inputs, streams_in)
                if not isinstance(outputs, self.Outputs):
                    raise TypeError(f"{self.name}: compute must return {self.Outputs.__name__}")
                self._check_ports(streams_out, self.outlets, "outlet")
                return outputs, streams_out

            cls.compute = checked

    def __init__(self, params: dict | BaseModel, *, fluid: str = "brine"):
        """Validate fixed SI parameters and resolve the fluid model once."""
        self.params = self.Params.model_validate(params)
        self.fluid_name = fluid
        self.fluid = self._resolve_fluid()

    def _resolve_fluid(self):
        overrides = {}
        for field, key in [("liquid_density", "RHOL"), ("liquid_viscosity", "VISL")]:
            value = getattr(self.params, field, None)
            if value is not None:
                overrides[key] = value
        return fluid.get_fluid(self.fluid_name, **overrides)

    def update_params(self, **changes) -> None:
        """Revalidate parameter changes and refresh dependent fluid properties."""
        self.params = self.Params.model_validate(self.params.model_dump() | changes)
        self.fluid = self._resolve_fluid()

    def _check_ports(self, streams, expected, kind):
        missing, extra = set(expected) - streams.keys(), streams.keys() - set(expected)
        if missing or extra:
            raise ValueError(
                f"{self.name}: {kind} ports missing={sorted(missing)}, extra={sorted(extra)}"
            )
        if any(not isinstance(s, Stream) for s in streams.values()):
            raise TypeError(f"{self.name}: {kind} ports must contain Stream objects")

    @abstractmethod
    def compute(
        self, inputs: BaseModel | dict, streams_in: dict[str, Stream]
    ) -> tuple[BaseModel, dict[str, Stream]]:
        """Compute SI outputs and streams from operating inputs and inlet streams."""

    def initial_state(self) -> Any:
        """Return the stateless default initial state."""
        return None

    def step(self, state, inputs, streams_in, dt: float):
        """Evaluate a stateless step of duration [s], leaving the state unchanged."""
        outputs, streams_out = self.compute(inputs, streams_in)
        return state, outputs, streams_out

    def health(self, predicted: BaseModel, measured: dict[str, float]) -> Health | None:
        """Return optional equipment health from SI measurements."""
        return None

    def capex(self) -> float | None:
        """Return optional capital expenditure; no default estimate is assumed."""
        return None

    @classmethod
    def schema(cls) -> dict:
        """Describe component identity, ports, SI models and monitoring capabilities."""
        return {
            "name": cls.name,
            "category": cls.category,
            "description": cls.description,
            "inlets": cls.inlets,
            "outlets": cls.outlets,
            "params": cls.Params.model_json_schema(),
            "inputs": cls.Inputs.model_json_schema(),
            "outputs": cls.Outputs.model_json_schema(),
            "soft_sensors": cls.soft_sensors,
            "calibratable": cls.calibratable,
            "stateful": cls.stateful,
        }
