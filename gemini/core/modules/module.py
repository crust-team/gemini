"""Registration-driven, PyTorch-style equipment modules."""

import importlib
import inspect
import json
import re
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from pathlib import Path
from typing import Literal

from pydantic_core import to_jsonable_python

from gemini.core import runtime
from gemini.core.physics import units
from gemini.core.types.bindings import ColumnInfo, DatedParams, ModuleBindings, utc
from gemini.core.types.cost import Cost
from gemini.core.types.declarations import (
    UNSET,
    Boundary,
    Control,
    Declaration,
    Inlet,
    Outlet,
    Output,
    Parameter,
)
from gemini.core.types.fluid import Fluid
from gemini.core.types.results import ModuleResult, Values

_evaluation = ContextVar("module_evaluation", default=None)
_output_call = ContextVar("module_output_call", default=None)
MODULE_REGISTRY = {}


def _snake_case(name):
    return re.sub(r"(?<!^)(?=[A-Z][a-z])|(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


class HookHandle:
    """Removable registration; removal is idempotent."""

    def __init__(self, hooks, key):
        """Retain the hook mapping and opaque registration key."""
        self._hooks, self._key = hooks, key

    def remove(self):
        """Stop calling this hook."""
        self._hooks.pop(self._key, None)


class Module:
    """Base class discovering declarations and child modules assigned in ``__init__``."""

    stateful = False
    fidelity: Literal["model", "simple", "passthrough"] = "model"
    repr_fields = ()

    def __init_subclass__(cls, **kwargs):
        """Derive metadata, register the class and wrap keyword-value construction."""
        super().__init_subclass__(**kwargs)
        if cls.__name__.startswith("_"):
            return
        doc = inspect.getdoc(cls)
        if not doc:
            raise TypeError(f"{cls.__name__} must have a class docstring")
        cls.name = _snake_case(cls.__name__)
        cls.description = doc.split("\n\n", 1)[0].replace("\n", " ")
        parts = cls.__module__.split(".")
        cls.category = (
            parts[parts.index("modules") + 1]
            if "modules" in parts and len(parts) > parts.index("modules") + 1
            else "user"
        )
        previous = MODULE_REGISTRY.get(cls.name)
        if previous is not None and previous is not cls:
            raise TypeError(
                f"Module registry name {cls.name!r} collides between "
                f"{previous.__module__}.{previous.__qualname__} and "
                f"{cls.__module__}.{cls.__qualname__}"
            )
        MODULE_REGISTRY[cls.name] = cls
        original = cls.__dict__.get("__init__")
        if original is None:
            return
        signature = inspect.signature(original)
        structural = {
            name
            for name, value in signature.parameters.items()
            if name != "self"
            and value.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        }

        @wraps(original)
        def initialise(self, *args, **kwargs):
            fluid = kwargs.pop("fluid", None)
            structural_values = {k: kwargs.pop(k) for k in tuple(kwargs) if k in structural}
            original(self, *args, **structural_values)
            if not hasattr(self, "_parameters"):
                raise RuntimeError(f"{cls.__name__}.__init__ must call super().__init__()")
            if fluid is not None:
                object.__setattr__(self, "_fluid", Fluid.model_validate(fluid))
                object.__setattr__(self, "fluid", self._resolve_fluid())
            self._finish_init(kwargs)

        cls.__init__ = initialise
        cls.__signature__ = signature.replace(
            parameters=[
                value
                for name, value in signature.parameters.items()
                if name == "self" or name in structural
            ]
            + [inspect.Parameter("values", inspect.Parameter.VAR_KEYWORD)]
        )

    def __init__(self):
        """Create independent ordered registries and run-owned metadata."""
        for name in (
            "_parameters",
            "_inlets",
            "_controls",
            "_boundaries",
            "_outputs",
            "_outlets",
            "_children",
            "_pre_hooks",
            "_hooks",
        ):
            object.__setattr__(self, name, {})
        object.__setattr__(self, "_path", "")
        object.__setattr__(self, "_initialising", True)
        object.__setattr__(self, "_fluid", runtime.get_default_fluid())
        object.__setattr__(self, "fluid", self._resolve_fluid())
        object.__setattr__(self, "bindings", {})
        object.__setattr__(self, "boundary", {})
        object.__setattr__(self, "param_history", [])
        object.__setattr__(self, "_active_from", None)
        object.__setattr__(self, "_active_params", {})
        object.__setattr__(self, "_param_overrides", {})
        object.__setattr__(self, "_forward_checked", False)

    def _finish_init(self, values):
        for path, value in values.items():
            parameter = self.get_parameter(path)
            parameter.set(value)
        object.__setattr__(self, "fluid", self._resolve_fluid())
        object.__setattr__(self, "_initialising", False)
        if not self.param_history:
            snapshot = {
                name: deepcopy(parameter.value)
                for name, parameter in self._parameters.items()
                if parameter.initialized
            }
            self.param_history = [DatedParams(params=to_jsonable_python(snapshot))]
            self._active_params = snapshot

    @property
    def path(self):
        """Return the assigned tree path or standalone derived name."""
        return self._path or self.name

    def _set_path(self, path):
        object.__setattr__(self, "_path", path)
        for declaration in self._declarations().values():
            declaration.bind(self, declaration.name)
        for name, child in self.named_children():
            child._set_path(f"{path}.{name}" if path else name)

    def _declarations(self):
        result = {}
        for registry in (
            self._parameters,
            self._inlets,
            self._controls,
            self._boundaries,
            self._outputs,
            self._outlets,
        ):
            result.update(registry)
        return result

    def __getattr__(self, name):
        """Resolve parameter values and registered declaration metadata."""
        parameters = self.__dict__.get("_parameters", {})
        if name in parameters:
            parameter = parameters[name]
            if not parameter.initialized:
                raise RuntimeError(f"{parameter.path}: parameter is uninitialized")
            return parameter.value
        for key in ("_inlets", "_controls", "_boundaries", "_outlets"):
            registry = self.__dict__.get(key, {})
            if name in registry:
                return registry[name]
        outputs = self.__dict__.get("_outputs", {})
        if name in outputs:
            active = _output_call.get()
            if active is not None and active[0] is self and name in active[1]:
                return active[1][name]
            return outputs[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        """Register declarations and children or assign declared call values."""
        if name.startswith("_") or "_parameters" not in self.__dict__:
            object.__setattr__(self, name, value)
            return
        if name in self._parameters and not isinstance(value, Declaration):
            self._parameters[name].set(value)
            object.__setattr__(self, "fluid", self._resolve_fluid())
            return
        if name in self._outputs and not isinstance(value, Declaration):
            active = _output_call.get()
            if active is None or active[0] is not self:
                raise RuntimeError(f"{self.path}.{name}: outputs may only be assigned in forward")
            active[1][name] = self._outputs[name].validate(value)
            return
        if isinstance(value, Declaration):
            if not self._initialising:
                raise RuntimeError(f"{self.path}: declarations may only be assigned in __init__")
            registries = {
                Parameter: self._parameters,
                Inlet: self._inlets,
                Control: self._controls,
                Boundary: self._boundaries,
                Output: self._outputs,
                Outlet: self._outlets,
            }
            existing = self._declarations().get(name)
            target = next(
                registry for kind, registry in registries.items() if isinstance(value, kind)
            )
            if existing is not None and existing is not value:
                raise TypeError(f"{self.path}.{name}: declaration is already registered")
            target[name] = value.bind(self, name)
            return
        if isinstance(value, Module):
            self.add_module(name, value)
            return
        if name in self._declarations():
            raise TypeError(f"{self.path}.{name}: cannot replace a declaration")
        if name in self._children:
            self._children.pop(name)
        object.__setattr__(self, name, value)

    def add_module(self, name, module):
        """Register an immediate child and reject ambiguous names or ownership cycles."""
        if not isinstance(module, Module):
            raise TypeError("child must be a Module")
        if not name or "." in name or name.startswith("_"):
            raise ValueError(f"Invalid child name {name!r}")
        if name in self._declarations():
            raise ValueError(f"Child name {name!r} conflicts with a declaration")
        if any(item is self for item in module.modules()):
            raise ValueError("Module ownership cannot contain a cycle")
        self._children[name] = module
        object.__setattr__(self, name, module)
        module._set_path(f"{self._path}.{name}" if self._path else name)

    def named_children(self):
        """Iterate immediate children in insertion order."""
        yield from self._children.items()

    def children(self):
        """Iterate immediate child modules."""
        yield from self._children.values()

    def named_modules(self, prefix=""):
        """Walk self and descendants once using dotted paths."""
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

    def _named(self, registry_name, recurse=False):
        for path, module in self.named_modules() if recurse else [("", self)]:
            for name, declaration in getattr(module, registry_name).items():
                yield f"{path}.{name}" if path else name, declaration

    def parameters(self, recurse=True):
        """Iterate parameter declarations."""
        for _, parameter in self._named("_parameters", recurse):
            yield parameter

    def named_parameters(self, recurse=True):
        """Iterate dotted names and parameter declarations."""
        yield from self._named("_parameters", recurse)

    def calibratable_parameters(self, recurse=True):
        """Return only parameters explicitly marked calibratable."""
        return [p for p in self.parameters(recurse) if p.calibratable]

    def _section(self, name, recurse=False):
        return dict(self._named(name, recurse))

    def inlets(self, recurse=False):
        """Return inlet declarations by local or dotted name."""
        return self._section("_inlets", recurse)

    def controls(self, recurse=False):
        """Return controllable input declarations."""
        return self._section("_controls", recurse)

    def boundaries(self, recurse=False):
        """Return external boundary declarations."""
        return self._section("_boundaries", recurse)

    def inputs(self, recurse=False):
        """Return controls followed by boundaries."""
        return self.controls(recurse) | self.boundaries(recurse)

    def outputs(self, recurse=False):
        """Return computed output declarations."""
        return self._section("_outputs", recurse)

    def outlets(self, recurse=False):
        """Return outgoing flow declarations."""
        return self._section("_outlets", recurse)

    def soft_sensors(self, recurse=False):
        """Return outputs marked as inferred measurements."""
        return {name: value for name, value in self.outputs(recurse).items() if value.soft_sensor}

    def get_parameter(self, path):
        """Return parameter metadata by local or dotted path."""
        module_path, _, name = path.rpartition(".")
        module = self.get_submodule(module_path)
        if name not in module._parameters:
            valid = ", ".join(module._parameters) or "<none>"
            raise ValueError(f"{self.path}: unknown parameter {path!r}; valid: {valid}")
        return module._parameters[name]

    def missing_parameters(self):
        """Return dotted paths of all uninitialized parameters."""
        return [name for name, value in self.named_parameters() if not value.initialized]

    @property
    def is_initialized(self):
        """Whether every parameter in this module tree has a value."""
        return not self.missing_parameters()

    def update_params(self, **changes):
        """Set validated local parameters as explicit overrides."""
        for name, value in changes.items():
            self.get_parameter(name).set(value)
        object.__setattr__(self, "fluid", self._resolve_fluid())

    def params_at(self, at):
        """Return the complete validated parameter mapping active at an instant."""
        eligible = [
            item
            for item in self.param_history
            if at is None or item.valid_from is None or item.valid_from <= utc(at)
        ]
        if not eligible:
            raise ValueError(f"{self.path}: no parameters valid at {at}")
        selected = max(eligible, key=lambda item: item.valid_from or utc("0001-01-01"))
        values = selected.params | self._param_overrides
        return {name: self._parameters[name].validate(value) for name, value in values.items()}

    def apply_params_at(self, at):
        """Apply dated parameter snapshots recursively while retaining explicit overrides."""
        for module in self.modules():
            values = module.params_at(at)
            for name, value in values.items():
                module._parameters[name].set(value, explicit=False)
            module._active_params = deepcopy(values)
            object.__setattr__(module, "fluid", module._resolve_fluid())

    def _resolve_fluid(self):
        overrides = {}
        parameters = self.__dict__.get("_parameters", {})
        for name in ("liquid_density", "liquid_viscosity"):
            if (
                name in parameters
                and parameters[name].initialized
                and parameters[name].value is not None
            ):
                overrides[name] = parameters[name].value
        return Fluid.model_validate(self._fluid.model_dump() | overrides)

    def _check_forward_signature(self):
        expected = set(self._inlets) | set(self._controls) | set(self._boundaries)
        signature = inspect.signature(self.forward)
        actual = {
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        }
        if actual != expected:
            raise TypeError(
                f"{type(self).__name__}.forward signature mismatch: "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )
        object.__setattr__(self, "_forward_checked", True)

    def forward(self, **kwargs):
        """Compute outputs and return declared outlets; subclasses implement this."""
        raise NotImplementedError(f"{type(self).__name__} has no forward method")

    def __call__(self, *args, **kwargs):
        """Validate inputs, record outputs and validate returned outlet flows."""
        missing = self.missing_parameters()
        if missing:
            raise RuntimeError(f"{self.path}: uninitialized parameters: {', '.join(missing)}")
        if not self._forward_checked:
            self._check_forward_signature()
        declarations = self._inlets | self._controls | self._boundaries
        signature = inspect.Signature(
            [
                inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                for name in declarations
            ]
        )
        try:
            bound = signature.bind_partial(*args, **kwargs)
        except TypeError as exc:
            raise TypeError(f"{self.path}: {exc}") from exc
        values = {}
        for name, declaration in declarations.items():
            if name in bound.arguments:
                values[name] = declaration.validate(bound.arguments[name])
            elif declaration.default is not UNSET:
                values[name] = declaration.validate(deepcopy(declaration.default))
            else:
                raise TypeError(f"{self.path}: missing required argument {name!r}")
        inlets = {name: values[name] for name in self._inlets}
        inputs = {name: values[name] for name in self._controls | self._boundaries}
        for fn in tuple(self._pre_hooks.values()):
            fn(self, inputs, inlets)
        children = {}
        parent = _evaluation.get()
        evaluation_token = _evaluation.set((self, children))
        recorded = {}
        output_token = _output_call.set((self, recorded))
        try:
            returned = self.forward(**values)
        finally:
            _output_call.reset(output_token)
            _evaluation.reset(evaluation_token)
        required = {name for name, output in self._outputs.items() if not output.optional}
        if required - recorded.keys():
            missing = sorted(required - recorded.keys())
            raise RuntimeError(f"{self.path}: required outputs left unassigned: {missing}")
        if returned is None and not self._outlets:
            returned = {}
        if not isinstance(returned, dict):
            raise TypeError(f"{self.path}: forward must return an outlet dict")
        missing_out = self._outlets.keys() - returned.keys()
        extra_out = returned.keys() - self._outlets.keys()
        if missing_out or extra_out:
            detail = f"missing={sorted(missing_out)}, extra={sorted(extra_out)}"
            raise ValueError(f"{self.path}: outlet names {detail}")
        outlets = {
            name: declaration.validate(returned[name])
            for name, declaration in self._outlets.items()
        }
        result = ModuleResult(
            outputs=Values(recorded, self._outputs),
            outlets=Values(outlets, self._outlets),
            inlets=inlets,
            inputs=inputs,
            children=children,
        )
        if parent is not None:
            owner, collected = parent
            prefix = owner._path + "." if owner._path else ""
            collected[self._path.removeprefix(prefix) or self.name] = result
        object.__setattr__(self, "last_result", result)
        object.__setattr__(self, "last_results", result.leaves())
        for fn in tuple(self._hooks.values()):
            fn(self, inputs, inlets, result)
        return result

    def initial_state(self):
        """Return independent states for stateful descendants, or None for a leaf."""
        states = {
            name: child.initial_state()
            for name, child in self.named_children()
            if child.stateful or child._children
        }
        return states or None

    def step(self, state, dt, **kwargs):
        """Evaluate a stateless step; stateful equipment may override this method."""
        if dt <= 0:
            raise ValueError("dt must be positive [s]")
        return state, self(**kwargs)

    def register_forward_pre_hook(self, fn):
        """Call ``fn`` before each forward evaluation."""
        key = object()
        self._pre_hooks[key] = fn
        return HookHandle(self._pre_hooks, key)

    def register_forward_hook(self, fn):
        """Call ``fn`` after each successful forward evaluation."""
        key = object()
        self._hooks[key] = fn
        return HookHandle(self._hooks, key)

    def health(self, predicted, measured):
        """Return optional equipment health; absence means no diagnostic model."""
        return None

    def state_dict(self):
        """Return JSON-safe parameter and fluid snapshots for the complete tree."""
        return {
            path: {
                "type": module.name,
                "params": {
                    name: to_jsonable_python(parameter.value)
                    for name, parameter in module._parameters.items()
                    if parameter.initialized
                },
                "fluid": module._fluid.model_dump(mode="json"),
            }
            for path, module in self.named_modules()
        }

    def load_state_dict(self, state, strict=True):
        """Validate every matching snapshot before atomically applying it."""
        modules = dict(self.named_modules())
        if strict and state.keys() != modules.keys():
            raise ValueError(
                f"{self.path}: state paths differ; missing={modules.keys() - state.keys()}, "
                f"unexpected={state.keys() - modules.keys()}"
            )
        pending = []
        for path in state.keys() & modules.keys():
            module, entry = modules[path], state[path]
            valid = {
                name: module.get_parameter(name).validate(value)
                for name, value in entry["params"].items()
            }
            unknown = entry["params"].keys() - module._parameters.keys()
            if unknown:
                raise ValueError(f"{module.path}: unknown state parameters {sorted(unknown)}")
            pending.append((module, valid, Fluid.model_validate(entry["fluid"])))
        for module, values, fluid in pending:
            for name, value in values.items():
                module._parameters[name].set(value, explicit=False)
            object.__setattr__(module, "_fluid", fluid)
            object.__setattr__(module, "fluid", module._resolve_fluid())
        return self

    @staticmethod
    def _class_name(cls):
        return f"{cls.__module__}:{cls.__qualname__}"

    @staticmethod
    def _import_class(name):
        module_name, qualname = name.split(":", 1)
        value = importlib.import_module(module_name)
        for part in qualname.split("."):
            value = getattr(value, part)
        if not isinstance(value, type) or not issubclass(value, Module):
            raise TypeError(f"Serialized class {name!r} is not a Module")
        return value

    def to_dict(self):
        """Return portable design, histories, bindings and boundary defaults."""
        modules = {}
        for path, module in self.named_modules():
            modules[path] = {
                "class": self._class_name(type(module)),
                "type": module.name,
                "params": self.state_dict()[path]["params"],
                "fluid": module._fluid.model_dump(mode="json"),
                "param_history": [item.model_dump(mode="json") for item in module.param_history],
                "param_overrides": to_jsonable_python(module._param_overrides),
                "active_from": (
                    module._active_from.isoformat() if module._active_from is not None else None
                ),
                "bindings": {
                    key: value.model_dump(mode="json") for key, value in module.bindings.items()
                },
                "boundary": to_jsonable_python(module.boundary),
            }
        return {"version": 1, "plant_type": self._class_name(type(self)), "modules": modules}

    @classmethod
    def from_dict(cls, data):
        """Construct the self-building tree, then fill its state and run metadata."""
        if data.get("version") != 1:
            raise ValueError(f"Unsupported plant format version {data.get('version')!r}")
        expected = cls._class_name(cls)
        if data.get("plant_type") != expected:
            raise ValueError(
                f"Stored plant type {data.get('plant_type')!r} does not match {expected!r}"
            )
        root = cls()
        entries = data.get("modules", {})
        modules = dict(root.named_modules())
        if entries.keys() != modules.keys():
            raise ValueError(
                f"Stored module paths differ; missing={modules.keys() - entries.keys()}, "
                f"unexpected={entries.keys() - modules.keys()}"
            )
        state = {}
        for path, module in modules.items():
            entry = entries[path]
            state[path] = {
                "type": module.name,
                "params": entry.get("params", {}),
                "fluid": entry.get("fluid", {}),
            }
        root.load_state_dict(state)
        for path, module in modules.items():
            entry = entries[path]
            module.param_history = [
                DatedParams.model_validate(item) for item in entry.get("param_history", [])
            ] or [DatedParams(params=entry.get("params", {}))]
            module._param_overrides = dict(entry.get("param_overrides", {}))
            module._active_from = (
                utc(entry["active_from"]) if entry.get("active_from") is not None else None
            )
            module._active_params = entry.get("params", {}).copy()
            module.bindings = {
                key: ModuleBindings.model_validate(value)
                for key, value in entry.get("bindings", {}).items()
            }
            module.boundary = dict(entry.get("boundary", {}))
        return root

    def save(self, path):
        """Save the complete portable module tree as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path):
        """Load a JSON plant file as this exact self-building class."""
        return cls.from_dict(json.loads(Path(path).read_text()))

    def column_units(self):
        """Collect raw binding units and reject conflicts."""
        columns = {}
        for path, bound in self.bindings.items():
            groups = [
                bound.controls,
                bound.boundaries,
                bound.measured,
                bound.state,
                *bound.inlets.values(),
            ]
            for group in groups:
                for field, binding in group.items():
                    info = ColumnInfo(unit=binding.unit)
                    if binding.column in columns and columns[binding.column] != info:
                        raise ValueError(f"{path}.{field}: conflicting binding unit")
                    columns[binding.column] = info
        return columns

    def extra_repr(self):
        """Display up to four initialized scalar parameters."""
        names = self.repr_fields or tuple(self._parameters)
        parts = []
        for name in names:
            parameter = self._parameters.get(name)
            if parameter is None or not parameter.initialized:
                continue
            value, unit = parameter.value, parameter.unit or ""
            if isinstance(value, (dict, list, tuple)) or value is None:
                continue
            if runtime.get_display_units() == "field":
                target = {"Pa": "bar", "K": "°C", "m3/s": "m3/h", "W": "kW"}.get(unit)
                if target:
                    value, unit = units.convert(value, unit, target), target
            shown = f"{value:.5g}" if isinstance(value, float) else str(value)
            parts.append(f"{name}={shown}{(' ' + unit) if unit and unit != '-' else ''}")
            if len(parts) == 4:
                break
        return ", ".join(parts)

    def __repr__(self):
        """Render a compact recursive module tree."""
        extra = self.extra_repr()
        if not self._children:
            return f"{type(self).__name__}({extra})"
        rows = [f"{type(self).__name__}({extra}"]
        for name, child in self.named_children():
            rows.append("  (" + name + "): " + repr(child).replace("\n", "\n  "))
        return "\n".join(rows + [")"])

    @classmethod
    def help(cls):
        """Return a declaration-oriented summary for interactive use."""
        try:
            module = cls()
        except TypeError:
            return f"{cls.description}\nCategory: {cls.category}"
        lines = [cls.description, f"Category: {cls.category}"]
        for title, values in (
            ("Parameters", module._parameters),
            ("Inlets", module._inlets),
            ("Controls", module._controls),
            ("Boundaries", module._boundaries),
            ("Outputs", module._outputs),
            ("Outlets", module._outlets),
        ):
            if not values:
                continue
            lines.append(f"\n{title}:")
            for name, value in values.items():
                details = [value.unit] if value.unit else []
                if isinstance(value, Parameter) and value.default is not UNSET:
                    details.append(f"default={value.default!r}")
                if isinstance(value, Parameter) and value.calibratable:
                    details.append("calibratable")
                if isinstance(value, Output) and value.soft_sensor:
                    details.append("soft sensor")
                lines.append(f"  {name}: {', '.join(details)}")
        return "\n".join(lines)

    def capex(self) -> Cost | None:
        """Return this module's capital cost when a subclass supplies one."""
        return None

    def cost(self) -> Cost | None:
        """Aggregate compatible descendant capital and operating costs."""
        costs = [value for module in self.modules() if (value := module.capex()) is not None]
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
