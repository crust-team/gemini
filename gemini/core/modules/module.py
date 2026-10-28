"""Composable, validated equipment modules and recursive parameter/state APIs."""

import inspect
from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import replace
from functools import wraps
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, RootModel, SerializeAsAny, ValidationError

from gemini.core.types.cost import Cost
from gemini.core.types.flows import Flow, Stream
from gemini.core.types.fluid import BRINE, Fluid
from gemini.core.types.results import ModuleResult, ParamRef

_evaluation = ContextVar("module_evaluation", default=None)


class HookHandle:
    """Removable registration; removal is idempotent."""

    def __init__(self, hooks, key):
        """Keep only the owning hook collection and registration key."""
        self._hooks, self._key = hooks, key

    def remove(self):
        """Stop calling this hook."""
        self._hooks.pop(self._key, None)


class EmptyModel(BaseModel):
    """Empty contract for composites and equipment without operating controls."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ChildInputs(RootModel[dict[str, Any]]):
    """Operating controls keyed by immediate child name."""

    root: dict[str, Any] = {}


class ChildOutputs(RootModel[dict[str, SerializeAsAny[BaseModel]]]):
    """Equipment outputs keyed by immediate child name."""


class Module(ABC):
    """Equipment contract with recursive composition, parameters, state and hooks."""

    name: ClassVar[str]
    category: ClassVar[str]
    description: ClassVar[str] = "Composable equipment model."
    Params = EmptyModel
    Inputs = EmptyModel
    Outputs = EmptyModel
    inlets: ClassVar[dict[str, type[Flow]]] = {}
    outlets: ClassVar[dict[str, type[Flow]]] = {}
    soft_sensors: ClassVar[tuple[str, ...]] = ()
    calibratable: ClassVar[tuple[str, ...]] = ()
    stateful: ClassVar[bool] = False
    fidelity: ClassVar[Literal["model", "simple", "passthrough"]] = "model"

    def __init_subclass__(cls, **kwargs):
        """Check metadata and retain validation for direct forward calls."""
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        for key in ("name", "category", "description", "Params", "Inputs", "Outputs"):
            if not hasattr(cls, key):
                raise TypeError(f"{cls.__name__} must define {key}")
        for key in ("Params", "Inputs", "Outputs"):
            if not issubclass(getattr(cls, key), BaseModel):
                raise TypeError(f"{cls.__name__}.{key} must be a Pydantic model")
        if cls.fidelity not in {"model", "simple", "passthrough"}:
            raise TypeError(f"{cls.name}: unknown fidelity {cls.fidelity}")
        for names, model in ((cls.soft_sensors, cls.Outputs), (cls.calibratable, cls.Params)):
            unknown = set(names) - model.model_fields.keys()
            if unknown:
                raise TypeError(f"{cls.name}: unknown schema fields {sorted(unknown)}")
        method = cls.__dict__.get("forward")
        if method is not None:

            @wraps(method)
            def checked(self, inputs, streams_in):
                inputs = self._validate_inputs(inputs)
                self._check_ports(streams_in, self.inlets, "inlet")
                result = method(self, inputs, streams_in)
                if not isinstance(result, ModuleResult) or not isinstance(
                    result.outputs, self.Outputs
                ):
                    raise TypeError(
                        f"{self.path}: forward must return ModuleResult "
                        f"with {self.Outputs.__name__}"
                    )
                self._check_ports(result.streams, self.outlets, "outlet")
                return result

            cls.forward = checked

    def __init__(self, params: dict | BaseModel | None = None, *, fluid: Fluid = BRINE):
        """Validate SI parameters and initialise independent child/hook collections."""
        object.__setattr__(self, "_children", {})
        object.__setattr__(self, "_pre_hooks", {})
        object.__setattr__(self, "_hooks", {})
        object.__setattr__(self, "_path", "")
        self.params = self.Params.model_validate({} if params is None else params)
        self._fluid = Fluid.model_validate(fluid)
        self.fluid = self._resolve_fluid()

    @property
    def path(self):
        """Return the assigned tree path or standalone equipment name."""
        return self._path or self.name

    def _set_path(self, path):
        object.__setattr__(self, "_path", path)
        for name, child in self.named_children():
            child._set_path(f"{path}.{name}" if path else name)

    def __setattr__(self, name, value):
        """Register assigned modules and unregister replaced children."""
        if name in {"inlets", "outlets"} and self.category != "plant":
            raise AttributeError(f"{self.path}: equipment ports are declared on the class")
        if isinstance(value, Module):
            self.add_module(name, value)
        else:
            if "_children" in self.__dict__:
                self._children.pop(name, None)
            object.__setattr__(self, name, value)

    def __delattr__(self, name):
        """Remove deleted child attributes from traversal."""
        object.__delattr__(self, name)
        self._children.pop(name, None)

    def add_module(self, name, module):
        """Register a child with an unambiguous local name, rejecting ownership cycles."""
        if not isinstance(module, Module):
            raise TypeError("child must be a Module")
        if not name or "." in name or name.startswith("_"):
            raise ValueError(f"Invalid child name {name!r}")
        if not hasattr(self, "_children"):
            raise RuntimeError("Call Module.__init__ before assigning children")
        if name not in self._children and hasattr(self, name):
            raise ValueError(f"Child name {name!r} conflicts with an existing attribute")
        if any(item is self for item in module.modules()):
            raise ValueError("Module ownership cannot contain a cycle")
        self._children[name] = module
        object.__setattr__(self, name, module)
        module._set_path(f"{self._path}.{name}" if self._path else name)

    def named_children(self):
        """Iterate registered immediate children in insertion order."""
        yield from self._children.items()

    def children(self):
        """Iterate immediate child modules."""
        yield from self._children.values()

    def named_modules(self, prefix=""):
        """Walk self and descendants once, using dotted paths."""
        seen = set()

        def walk(module, path):
            if id(module) in seen:
                return
            seen.add(id(module))
            yield path, module
            for name, child in module.named_children():
                yield from walk(child, f"{path}.{name}" if path else name)

        yield from walk(self, prefix)

    def modules(self):
        """Walk self and all unique descendants."""
        for _, module in self.named_modules():
            yield module

    def get_submodule(self, path):
        """Resolve a dotted descendant path; the empty path denotes self."""
        module = self
        for part in path.split(".") if path else ():
            if part not in module._children:
                raise ValueError(f"{self.path}: unknown module path {path!r}")
            module = module._children[part]
        return module

    def apply(self, fn):
        """Apply a visitor to every module, descendants before parents."""
        for module in reversed(list(self.modules())):
            fn(module)
        return self

    def _resolve_fluid(self):
        overrides = {}
        for field, key in (
            ("liquid_density", "liquid_density"),
            ("liquid_viscosity", "liquid_viscosity"),
        ):
            value = getattr(self.params, field, None)
            if value is not None:
                overrides[key] = value
        return Fluid.model_validate(self._fluid.model_dump() | overrides)

    def update_params(self, **changes):
        """Revalidate design changes before replacing the parameter snapshot."""
        self.params = self.Params.model_validate(self.params.model_dump() | changes)
        self.fluid = self._resolve_fluid()

    def _validate_inputs(self, inputs):
        try:
            return self.Inputs.model_validate({} if inputs is None else inputs)
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                self.path, exc.errors(include_url=False)
            ) from exc

    def _check_ports(self, streams, expected, kind):
        missing, extra = set(expected) - streams.keys(), streams.keys() - set(expected)
        if missing or extra:
            raise ValueError(
                f"{self.path}: {kind} ports missing={sorted(missing)}, extra={sorted(extra)}"
            )
        for name, value in streams.items():
            if not isinstance(value, expected[name]):
                raise TypeError(f"{self.path}: {kind} {name} requires {expected[name].__name__}")

    @abstractmethod
    def forward(self, inputs, streams_in) -> ModuleResult:
        """Calculate SI outputs and outgoing streams."""

    def __call__(self, inputs=None, streams_in=None, **streams):
        """Validate a forward evaluation and notify observers in registration order."""
        inputs = self._validate_inputs(inputs)
        inlet = dict(streams_in or {})
        overlap = inlet.keys() & streams.keys()
        if overlap:
            raise ValueError(f"{self.path}: duplicate streams {sorted(overlap)}")
        inlet.update(streams)
        self._check_ports(inlet, self.inlets, "inlet")
        for fn in tuple(self._pre_hooks.values()):
            fn(self, inputs, inlet)
        children = {}
        parent = _evaluation.get()
        token = _evaluation.set((self, children))
        try:
            result = self.forward(inputs, inlet)
        finally:
            _evaluation.reset(token)
        result = replace(result, inlets=inlet, inputs=inputs, children=children)
        if parent is not None:
            owner, collected = parent
            prefix = owner._path + "." if owner._path else ""
            collected[self._path.removeprefix(prefix) or self.name] = result
        self.last_result = result
        self.last_results = result.leaves()
        for fn in tuple(self._hooks.values()):
            fn(self, inputs, inlet, result)
        return result

    def named_params(self, recurse=True):
        """Iterate parameter values with their owning module paths."""
        for path, module in self.named_modules() if recurse else [("", self)]:
            for field in type(module.params).model_fields:
                yield f"{path}.{field}" if path else field, getattr(module.params, field)

    def calibratable_params(self, recurse=True):
        """Return fit parameters and Pydantic scalar bounds (inclusive numerical limits)."""
        refs = []
        for path, module in self.named_modules() if recurse else [("", self)]:
            for field in module.calibratable:
                low, high = float("-inf"), float("inf")
                bounded = False
                for constraint in module.Params.model_fields[field].metadata:
                    for key in ("gt", "ge", "lt", "le"):
                        value = getattr(constraint, key, None)
                        if value is not None:
                            bounded = True
                            if key in ("gt", "ge"):
                                low = max(low, value)
                            else:
                                high = min(high, value)
                refs.append(
                    ParamRef(
                        f"{path}.{field}" if path else field,
                        path,
                        field,
                        getattr(module.params, field),
                        (low, high) if bounded else None,
                    )
                )
        return refs

    def _param_owner(self, path):
        module_path, _, field = path.rpartition(".")
        module = self.get_submodule(module_path)
        if field not in module.Params.model_fields:
            raise ValueError(f"{self.path}: unknown parameter {path!r}")
        return module, field

    def get_param(self, path):
        """Read a parameter using a dotted path."""
        module, field = self._param_owner(path)
        return getattr(module.params, field)

    def set_param(self, path, value):
        """Replace a parameter only after its owning Params validates."""
        module, field = self._param_owner(path)
        module.update_params(**{field: value})

    def state_dict(self):
        """Return JSON-safe design snapshots, including the root module."""
        return {
            path: {
                "type": module.name,
                "params": module.params.model_dump(mode="json"),
                "fluid": module._fluid.model_dump(mode="json"),
            }
            for path, module in self.named_modules()
        }

    def load_state_dict(self, state, strict=True):
        """Validate all matching snapshots before atomically applying parameter changes."""
        modules = dict(self.named_modules())
        if strict and state.keys() != modules.keys():
            raise ValueError(
                f"{self.path}: state paths differ; missing={modules.keys() - state.keys()}, "
                f"unexpected={state.keys() - modules.keys()}"
            )
        pending = []
        for path in state.keys() & modules.keys():
            module, entry = modules[path], state[path]
            if entry["type"] != module.name:
                raise ValueError(f"{module.path}: state type {entry['type']!r} != {module.name!r}")
            pending.append(
                (
                    module,
                    module.Params.model_validate(entry["params"]),
                    Fluid.model_validate(entry["fluid"]),
                )
            )
        for module, params, dtype in pending:
            module.params = params
            module._fluid = dtype
            module.fluid = module._resolve_fluid()

    def initial_state(self):
        """Return independent states for stateful descendants, or None for a leaf."""
        states = {
            name: child.initial_state()
            for name, child in self.named_children()
            if child.stateful or child._children
        }
        return states or None

    def step(self, state, inputs, streams_in, dt):
        """Evaluate a stateless step; stateful equipment overrides this method."""
        if dt <= 0:
            raise ValueError("dt must be positive [s]")
        return state, self(inputs, streams_in)

    def register_forward_pre_hook(self, fn):
        """Observe validated inputs before evaluation."""
        key = object()
        self._pre_hooks[key] = fn
        return HookHandle(self._pre_hooks, key)

    def register_forward_hook(self, fn):
        """Observe validated results after evaluation."""
        key = object()
        self._hooks[key] = fn
        return HookHandle(self._hooks, key)

    def health(self, predicted, measured):
        """Return optional equipment health; absence means no diagnostic model."""
        return None

    def health_report(self, results, measured):
        """Collect available health diagnostics recursively by module path."""
        report = {}
        for path, module in self.named_modules():
            if path in results:
                health = module.health(results[path].outputs, measured.get(path, {}))
                if health is not None:
                    report[path] = health
        return report

    def capex(self) -> Cost | None:
        """Return optional capital expenditure when a correlation is available."""
        return None

    def cost(self) -> Cost | None:
        """Sum independently sourced costs; never combine currencies or price years."""
        costs = [cost for module in self.modules() if (cost := module.capex()) is not None]
        if not costs:
            return None
        first = costs[0]
        if any((c.currency, c.price_year) != (first.currency, first.price_year) for c in costs):
            raise ValueError("Costs require the same currency and price year")
        return Cost(
            capex=sum(c.capex for c in costs),
            opex_fixed=sum(c.opex_fixed for c in costs),
            opex_variable=sum(c.opex_variable for c in costs),
            currency=first.currency,
            price_year=first.price_year,
            source="; ".join(dict.fromkeys(c.source for c in costs)),
        )

    @staticmethod
    def _field_schema(model):
        """Retain JSON schema, adding explicit names, bounds and nullable defaults."""
        schema = model.model_json_schema()
        for name, field in schema.get("properties", {}).items():
            variants = field.get("anyOf", [field])
            value = next((v for v in variants if v.get("type") != "null"), field)
            field["name"] = name
            field["quantity"] = value.get("quantity", field.get("quantity"))
            field["unit"] = value.get("unit", field.get("unit"))
            field["bounds"] = {
                k: value[k]
                for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
                if k in value
            }
            field.setdefault("description", "")
            field.setdefault("default", None)
        return schema

    @classmethod
    def schema(cls):
        """Describe identity, fidelity, ports and all validated contracts."""
        return dict(
            name=cls.name,
            category=cls.category,
            description=cls.description,
            fidelity=cls.fidelity,
            inlets={k: v.__name__ for k, v in cls.inlets.items()},
            outlets={k: v.__name__ for k, v in cls.outlets.items()},
            params=cls._field_schema(cls.Params),
            inputs=cls._field_schema(cls.Inputs),
            outputs=cls._field_schema(cls.Outputs),
            soft_sensors=cls.soft_sensors,
            calibratable=cls.calibratable,
            stateful=cls.stateful,
        )


class Sequential(Module):
    """Chain single-inlet/single-outlet modules with controls keyed by index or name."""

    name = "sequential"
    category = "plant"
    Inputs = ChildInputs
    Outputs = ChildOutputs

    def __init__(self, *modules):
        """Accept positional modules or a single ordered mapping of names to modules."""
        super().__init__()
        items = (
            modules[0].items()
            if len(modules) == 1 and isinstance(modules[0], dict)
            else enumerate(modules)
        )
        for name, module in items:
            if (
                len(module.inlets) != 1
                or len([t for t in module.outlets.values() if t is Stream]) != 1
            ):
                raise ValueError("Sequential children require exactly one inlet and outlet")
            self.add_module(str(name), module)
        children = list(self.children())
        if not children:
            raise ValueError("Sequential requires at least one child")
        self.inlets = children[0].inlets
        self.outlets = {k: t for k, t in children[-1].outlets.items() if t is Stream}

    def _chain(self, inputs, streams_in, state=None, dt=None):
        if inputs.root.keys() - self._children.keys():
            raise ValueError(f"{self.path}: unknown child inputs")
        stream = streams_in[next(iter(self.inlets))]
        outputs, next_state = {}, {}
        for name, child in self.named_children():
            inlet = {next(iter(child.inlets)): stream}
            if dt is not None and (child.stateful or child._children):
                next_state[name], result = child.step(
                    (state or {}).get(name), inputs.root.get(name), inlet, dt
                )
            else:
                result = child(inputs.root.get(name), inlet)
            stream = result.streams[next(k for k, t in child.outlets.items() if t is Stream)]
            outputs[name] = result.outputs
        return next_state or state, ModuleResult(
            self.Outputs(outputs), {next(iter(self.outlets)): stream}
        )

    def forward(self, inputs, streams_in):
        """Pass each outgoing stream to the next child."""
        return self._chain(inputs, streams_in)[1]

    def step(self, state, inputs, streams_in, dt):
        """Advance each stateful child with its own state and validate external ports."""
        if dt <= 0:
            raise ValueError("dt must be positive [s]")
        inputs = self._validate_inputs(inputs)
        self._check_ports(streams_in, self.inlets, "inlet")
        return self._chain(inputs, streams_in, state, dt)
