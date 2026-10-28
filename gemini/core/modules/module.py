"""Registration-driven, PyTorch-style equipment modules."""

import ast
import importlib
import inspect
import json
import re
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from difflib import get_close_matches
from functools import wraps
from pathlib import Path
from textwrap import dedent
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
_input_call = ContextVar("module_input_call", default=None)
_inlet_call = ContextVar("module_inlet_call", default=None)
_outputs_enabled = ContextVar("module_outputs_enabled", default=True)
MODULE_REGISTRY = {}


def _snake_case(name):
    return re.sub(r"(?<!^)(?=[A-Z][a-z])|(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


@contextmanager
def no_outputs():
    """Skip output computation and hooks within a nestable context or decorator."""
    token = _outputs_enabled.set(False)
    try:
        yield
    finally:
        _outputs_enabled.reset(token)


def outputs_enabled():
    """Return whether the current context records computed outputs."""
    return _outputs_enabled.get()


def _declared_port_names(cls):
    """Read conventional inlet/outlet assignments without constructing the class."""
    names = set()
    for base in reversed(cls.__mro__):
        method = base.__dict__.get("__init__")
        if method is None:
            continue
        try:
            tree = ast.parse(dedent(inspect.getsource(method)))
        except (OSError, TypeError, IndentationError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Call):
                continue
            called = value.func
            called_name = (
                called.id if isinstance(called, ast.Name) else getattr(called, "attr", None)
            )
            if called_name not in {"Inlet", "Outlet"}:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    names.add(target.attr)
    return names


def _named_parameters(fn, *, skip=()):
    signature = inspect.signature(fn)
    names = []
    for name, parameter in signature.parameters.items():
        if name in skip:
            continue
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            raise TypeError(f"{fn.__qualname__}: variadic parameters are not supported")
        names.append(name)
    return tuple(names)


class RemovableHandle:
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
        compute = cls.__dict__.get("_compute_outputs")
        if compute is not None:
            names = _named_parameters(compute, skip=("self",))
            valid = _declared_port_names(cls)
            bad = [name for name in names if name not in valid]
            if valid and bad:
                raise TypeError(
                    f"{cls.__name__}._compute_outputs has unknown inlet/outlet {bad[0]!r}; "
                    f"valid names: {', '.join(sorted(valid)) or '<none>'}"
                )
            cls._compute_output_args = names
        elif not hasattr(cls, "_compute_output_args"):
            cls._compute_output_args = ()
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
            valid = set(self._inlets) | set(self._outlets)
            bad = [name for name in type(self)._compute_output_args if name not in valid]
            if bad:
                raise TypeError(
                    f"{type(self).__name__}._compute_outputs has unknown inlet/outlet "
                    f"{bad[0]!r}; valid names: {', '.join(sorted(valid)) or '<none>'}"
                )
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
            object.__setattr__(
                self,
                name,
                OrderedDict() if name in {"_pre_hooks", "_hooks"} else {},
            )
        object.__setattr__(self, "_input_values", {})
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
        """Resolve parameter, current input and registered port values."""
        parameters = self.__dict__.get("_parameters", {})
        if name in parameters:
            parameter = parameters[name]
            if not parameter.initialized:
                raise RuntimeError(f"{parameter.path}: parameter is uninitialized")
            return parameter.value
        for key in ("_controls", "_boundaries"):
            registry = self.__dict__.get(key, {})
            if name in registry:
                active = _input_call.get()
                if active is not None and active[0] is self and name in active[1]:
                    return active[1][name]
                persistent = self.__dict__.get("_input_values", {})
                if name in persistent:
                    return persistent[name]
                declaration = registry[name]
                if declaration.default is not UNSET:
                    return declaration.validate(deepcopy(declaration.default))
                unit = declaration.unit or "-"
                raise RuntimeError(
                    f"{declaration.path}: {declaration.section} {name!r} has no value [{unit}]"
                )
        for key in ("_inlets", "_outlets"):
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
        inputs = self._controls | self._boundaries
        if name in inputs and not isinstance(value, Declaration):
            validated = inputs[name].validate(value)
            active = _input_call.get()
            if active is not None and active[0] is self:
                active[1][name] = validated
            else:
                self._input_values[name] = validated
            return
        if name in self._outputs and not isinstance(value, Declaration):
            active = _output_call.get()
            if active is None or active[0] is not self:
                raise RuntimeError(
                    f"{self.path}.{name}: outputs may only be assigned while computing outputs"
                )
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

    def _get_input(self, path, registry_name, kind):
        module_path, _, name = path.rpartition(".")
        module = self.get_submodule(module_path)
        registry = getattr(module, registry_name)
        if name not in registry:
            valid = ", ".join(registry) or "<none>"
            raise ValueError(f"{self.path}: unknown {kind} {path!r}; valid: {valid}")
        return registry[name]

    def get_control(self, path):
        """Return control metadata by local or dotted path."""
        return self._get_input(path, "_controls", "control")

    def get_boundary(self, path):
        """Return boundary metadata by local or dotted path."""
        return self._get_input(path, "_boundaries", "boundary")

    def set_inputs(self, mapping):
        """Persist validated controls and boundaries addressed by relative dotted path."""
        declarations = self.inputs(recurse=True)
        pending = []
        for path, value in mapping.items():
            if path not in declarations:
                suggestion = get_close_matches(path, declarations, n=1)
                detail = f"; did you mean {suggestion[0]!r}?" if suggestion else ""
                valid = ", ".join(declarations) or "<none>"
                raise ValueError(
                    f"{self.path}: unknown control/boundary path {path!r}{detail}; valid: {valid}"
                )
            declaration = declarations[path]
            pending.append((declaration.owner, declaration.name, declaration.validate(value)))
        for owner, name, value in pending:
            owner._input_values[name] = value
        return self

    def missing_parameters(self):
        """Return dotted paths of all uninitialized parameters."""
        return [name for name, value in self.named_parameters() if not value.initialized]

    @property
    def is_initialized(self):
        """Whether every parameter in this module tree has a value."""
        return not self.missing_parameters()

    @property
    def is_leaf(self):
        """Whether this module owns no child modules."""
        return not self._children

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
        expected = list(self._inlets)
        signature = inspect.signature(self.forward)
        actual = [
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]
        if actual != expected:
            raise TypeError(
                f"{type(self).__name__}.forward signature mismatch: "
                f"expected={expected}, actual={actual}"
            )
        object.__setattr__(self, "_forward_checked", True)

    def forward(self, **kwargs):
        """Move inlet fluids to declared outlets; subclasses implement this."""
        raise NotImplementedError(f"{type(self).__name__} has no forward method")

    def _compute_outputs(self):
        """Compute leaf outputs after ``forward``; overrides never call ``super()``."""

    def _split_call_args(self, args, kwargs):
        inlet_names = list(self._inlets)
        valid_names = inlet_names + list(self._controls) + list(self._boundaries)
        if len(args) > len(inlet_names):
            raise TypeError(
                f"{self.path}: expected at most {len(inlet_names)} positional inlet arguments, "
                f"got {len(args)}; valid: {', '.join(valid_names) or '<none>'}"
            )
        unknown = kwargs.keys() - set(valid_names)
        if unknown:
            raise TypeError(
                f"{self.path}: unexpected keyword(s) {sorted(unknown)}; "
                f"valid inlets, controls and boundaries: {', '.join(valid_names) or '<none>'}"
            )
        values = dict(zip(inlet_names, args))
        duplicate = values.keys() & kwargs.keys()
        if duplicate:
            name = next(iter(duplicate))
            raise TypeError(f"{self.path}: multiple values for inlet {name!r}")
        values.update({name: kwargs[name] for name in inlet_names if name in kwargs})
        missing = [name for name in inlet_names if name not in values]
        if missing:
            raise TypeError(f"{self.path}: missing required inlet(s): {', '.join(missing)}")
        inlets = {name: self._inlets[name].validate(values[name]) for name in inlet_names}
        inputs = {
            name: kwargs[name] for name in self._controls | self._boundaries if name in kwargs
        }
        return inlets, inputs

    @contextmanager
    def _apply_inputs(self, supplied):
        resolved = {}
        for name, declaration in (self._controls | self._boundaries).items():
            if name in supplied:
                value = supplied[name]
            elif name in self._input_values:
                value = self._input_values[name]
            elif declaration.default is not UNSET:
                value = deepcopy(declaration.default)
            else:
                unit = declaration.unit or "-"
                raise TypeError(
                    f"{declaration.path}: missing required {declaration.section} "
                    f"{name!r} [{unit}]"
                )
            resolved[name] = declaration.validate(value)
        token = _input_call.set((self, resolved))
        try:
            yield resolved
        finally:
            _input_call.reset(token)

    def _current_inlets(self):
        active = _inlet_call.get()
        return active[1] if active is not None and active[0] is self else {}

    def _call_by_name(self, fn, inlets, outlets, *, names=None, **extra):
        """Call a cached output callback with only the inlet/outlet names it requests."""
        selected = type(self)._compute_output_args if names is None else names
        available = dict(inlets) | dict(outlets) | extra
        arguments = {name: available[name] for name in selected}
        arguments.update(extra)
        return fn(**arguments)

    def _formula_candidates(self):
        candidates = []
        for path, module in self.named_modules():
            if not path:
                continue
            candidates.extend(f"{path}.{name}" for name in module._outputs)
            for name, outlet in module._outlets.items():
                fields = getattr(outlet.kind, "model_fields", {})
                candidates.extend(f"{path}.{name}.{field}" for field in fields)
        return candidates

    def _resolve_of(self, target):
        parts = target.split(".")
        module = None
        module_path = ""
        remainder = []
        for size in range(len(parts) - 1, 0, -1):
            try:
                candidate = self.get_submodule(".".join(parts[:size]))
            except ValueError:
                continue
            module, module_path, remainder = candidate, ".".join(parts[:size]), parts[size:]
            break
        declaration = None
        access = None
        if module is not None and len(remainder) == 1 and remainder[0] in module._outputs:
            declaration = module._outputs[remainder[0]]
            access = ("output", remainder[0], None)
        elif module is not None and len(remainder) == 2 and remainder[0] in module._outlets:
            outlet = module._outlets[remainder[0]]
            field = getattr(outlet.kind, "model_fields", {}).get(remainder[1])
            if field is not None:
                declaration = Output(field.annotation)
                access = ("outlet", remainder[0], remainder[1])
        if declaration is None:
            candidates = self._formula_candidates()
            suggestion = get_close_matches(target, candidates, n=1)
            detail = f"; did you mean {suggestion[0]!r}?" if suggestion else ""
            raise ValueError(f"{self.path}: unknown output formula path {target!r}{detail}")
        return module_path, access, declaration

    def _resolve_formula_outputs(self):
        seen = set()
        for name, output in self._outputs.items():
            if output.formula is None:
                seen.add(name)
                continue
            if output._resolved_formula is not None:
                seen.add(name)
                continue
            kind, *arguments = output.formula
            if kind == "of":
                module_path, access, declaration = self._resolve_of(arguments[0])
                output.infer_kind(declaration)
                output._resolved_formula = (kind, module_path, access)
            elif kind == "total":
                target = arguments[0]
                declarations = [
                    module._outputs[target]
                    for path, module in self.named_modules()
                    if path and module.is_leaf and target in module._outputs
                ]
                if not declarations:
                    names = sorted(
                        {
                            field
                            for path, module in self.named_modules()
                            if path and module.is_leaf
                            for field in module._outputs
                        }
                    )
                    suggestion = get_close_matches(target, names, n=1)
                    detail = f"; did you mean {suggestion[0]!r}?" if suggestion else ""
                    raise ValueError(
                        f"{self.path}: no descendant leaf declares output {target!r}{detail}"
                    )
                units = {declaration.unit for declaration in declarations}
                if len(units) != 1:
                    raise TypeError(
                        f"{self.path}.{name}: Output.total({target!r}) has differing units "
                        f"{sorted(str(unit) for unit in units)}"
                    )
                if any(
                    declaration.quantity not in {"power", "mass_flow"}
                    for declaration in declarations
                ):
                    raise TypeError(
                        f"{self.path}.{name}: Output.total({target!r}) requires an additive "
                        "power, heat-flow or mass-flow quantity"
                    )
                output.infer_kind(declarations[0])
                output._resolved_formula = (kind, target)
            else:
                numerator, denominator = arguments
                for reference in (numerator, denominator):
                    if reference not in seen:
                        suggestion = get_close_matches(reference, seen, n=1)
                        detail = f"; did you mean {suggestion[0]!r}?" if suggestion else ""
                        raise ValueError(
                            f"{self.path}.{name}: ratio references unavailable earlier output "
                            f"{reference!r}{detail}"
                        )
                output._resolved_formula = (kind, numerator, denominator)
            seen.add(name)

    @staticmethod
    def _recorded_calls(call_records, prefix=""):
        for path, result in call_records:
            full_path = f"{prefix}.{path}" if prefix else path
            yield full_path, result
            yield from Module._recorded_calls(result.call_records, full_path)

    def _compute_formula_outputs(self, call_records):
        calls = list(self._recorded_calls(call_records))
        for name, output in self._outputs.items():
            if output.formula is None:
                continue
            kind, *arguments = output._resolved_formula
            if kind == "of":
                module_path, (section, port, field) = arguments
                matches = [result for path, result in calls if path == module_path]
                if len(matches) != 1:
                    raise RuntimeError(
                        f"{self.path}.{name}: descendant {module_path!r} was called "
                        f"{len(matches)} times; expected exactly once"
                    )
                values = matches[0].outputs if section == "output" else matches[0].outlets
                value = values[port]
                setattr(self, name, getattr(value, field) if field is not None else value)
            elif kind == "total":
                target = arguments[0]
                value = sum(
                    result.outputs[target]
                    for _, result in calls
                    if result.is_leaf and target in result.outputs
                )
                setattr(self, name, value)
            else:
                numerator, denominator = arguments
                divisor = getattr(self, denominator)
                setattr(self, name, None if divisor == 0 else getattr(self, numerator) / divisor)

    def _check_outputs(self, recorded):
        missing = sorted(self._outputs.keys() - recorded.keys())
        if missing:
            raise RuntimeError(f"{self.path}: outputs left unassigned: {missing}")

    def __call__(self, *args, **kwargs):
        """Apply controls and boundaries, run hooks/forward, and validate outlets."""
        missing = self.missing_parameters()
        if missing:
            raise RuntimeError(f"{self.path}: uninitialized parameters: {', '.join(missing)}")
        if not self._forward_checked:
            self._check_forward_signature()
        self._resolve_formula_outputs()
        inlets, supplied = self._split_call_args(args, kwargs)
        children, call_records, recorded = {}, [], {}
        parent = _evaluation.get()
        inlet_token = _inlet_call.set((self, inlets))
        try:
            with self._apply_inputs(supplied) as inputs:
                for fn in tuple(self._pre_hooks.values()):
                    fn(self)
                evaluation_token = _evaluation.set((self, children, call_records))
                output_token = _output_call.set((self, recorded)) if outputs_enabled() else None
                try:
                    returned = self.forward(**inlets)
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
                    if outputs_enabled():
                        self._call_by_name(self._compute_outputs, inlets, outlets)
                        self._compute_formula_outputs(call_records)
                        for fn, names in tuple(self._hooks.values()):
                            self._call_by_name(fn, inlets, outlets, names=names, module=self)
                        self._check_outputs(recorded)
                finally:
                    if output_token is not None:
                        _output_call.reset(output_token)
                    _evaluation.reset(evaluation_token)
                inputs = dict(inputs)
        finally:
            _inlet_call.reset(inlet_token)
        result = ModuleResult(
            outputs=Values(recorded, self._outputs),
            outlets=Values(outlets, self._outlets),
            inlets=inlets,
            inputs=inputs,
            children=children,
            call_records=tuple(call_records),
            is_leaf=self.is_leaf,
        )
        if parent is not None:
            owner, collected, calls = parent
            prefix = owner._path + "." if owner._path else ""
            relative = self._path.removeprefix(prefix) or self.name
            collected[relative] = result
            calls.append((relative, result))
        object.__setattr__(self, "last_result", result)
        object.__setattr__(self, "last_results", result.leaves())
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
        return RemovableHandle(self._pre_hooks, key)

    def register_forward_hook(self, fn):
        """Call ``fn(module, named inlets/outlets...)`` after output computation."""
        parameters = _named_parameters(fn)
        if not parameters or parameters[0] != "module":
            raise TypeError("forward hooks must name their first parameter 'module'")
        names = parameters[1:]
        valid = set(self._inlets) | set(self._outlets)
        bad = [name for name in names if name not in valid]
        if bad:
            raise TypeError(
                f"{self.path}: forward hook has unknown inlet/outlet {bad[0]!r}; "
                f"valid names: {', '.join(sorted(valid)) or '<none>'}"
            )
        key = object()
        self._hooks[key] = (fn, names)
        return RemovableHandle(self._hooks, key)

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
