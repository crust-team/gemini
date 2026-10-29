"""Equipment modules: declarations and children registered in ``__init__``, called with inlets.

A module registers what ``__init__`` assigns: ``Parameter``, ``Inlet``, ``Control``, ``Boundary``,
``Output`` and ``Outlet`` declarations go to ordered registries and ``Module`` values become
children with dotted paths. Calling a module validates the inlets, applies controls and
boundaries, runs the forward pre-hooks, ``forward``, the leaf ``_compute_outputs`` or composite
output formulas and the forward hooks, then returns a ``ModuleResult``.

The values of one call (resolved controls and boundaries, recorded outputs and the results of
child calls) live in a ``_Call`` record held in the ``_current_call`` context variable while the
call runs; it is the only per-call state. ``no_outputs()`` is the only other context setting.
"""

import importlib
import inspect
from collections.abc import Mapping
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field

from pydantic_core import to_jsonable_python

from gemini.core import runtime
from gemini.core.physics import units
from gemini.core.types.bindings import DatedParams, ModuleBindings
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
from gemini.core.types.ports import Ports
from gemini.core.types.results import ModuleResult, Values
from gemini.errors import (
    CallError,
    ConfigurationError,
    DeclarationError,
    FormulaError,
    MissingValueError,
    OutletError,
    OutputError,
    PlantFormatError,
    UnknownNameError,
)
from gemini.utils.context import ContextSetting
from gemini.utils.files import read_json, write_json
from gemini.utils.hooks import RemovableHandle, has_signature
from gemini.utils.strings import (
    did_you_mean,
    first_paragraph,
    join_names,
    join_path,
    snake_case,
    split_path,
)
from gemini.utils.time import to_utc

_current_call = ContextVar("module_call", default=None)
_outputs_enabled = ContextVar("module_outputs_enabled", default=True)
_EARLIEST = to_utc("0001-01-01")
_ADDITIVE_QUANTITIES = {"power", "mass_flow"}
_FIELD_DISPLAY_UNITS = {"Pa": "bar", "K": "°C", "m3/s": "m3/h", "W": "kW"}
_REGISTRIES = (
    (Parameter, "_parameters"),
    (Inlet, "_inlets"),
    (Control, "_controls"),
    (Boundary, "_boundaries"),
    (Output, "_outputs"),
    (Outlet, "_outlets"),
)


def no_outputs():
    """Skip output computation and hooks within a nestable context or decorator."""
    return ContextSetting(_outputs_enabled, lambda current: False)


def outputs_enabled():
    """Return whether the current context records computed outputs."""
    return _outputs_enabled.get()


def class_path(cls):
    """Return the ``module:qualname`` path that plant files and checkpoints store for a class.

    Together with ``import_class`` this is the only import-by-string in GEMINI: a saved plant or
    checkpoint must name the handwritten plant class that rebuilds its module tree.
    """
    return f"{cls.__module__}:{cls.__qualname__}"


def import_class(path):
    """Import the ``Module`` subclass named by a ``class_path`` string."""
    module_name, qualname = path.split(":", 1)
    value = importlib.import_module(module_name)
    for part in qualname.split("."):
        value = getattr(value, part)
    if not isinstance(value, type) or not issubclass(value, Module):
        raise PlantFormatError(f"Serialized class {path!r} is not a Module")
    return value


@dataclass
class _Call:
    """Values of one module call in progress.

    ``outputs`` is ``None`` when outputs are disabled. ``call_records`` collects the results of
    every child call made during this call, in call order. ``parent`` is the enclosing call.
    """

    module: "Module"
    inputs: dict
    outputs: dict | None
    parent: "_Call | None"
    call_records: list = field(default_factory=list)

    def owned_by(self, module):
        """Return the innermost call of ``module`` in this chain, or ``None``."""
        call = self
        while call is not None and call.module is not module:
            call = call.parent
        return call


def _active_call(module):
    """Return the running call of ``module``, or ``None`` outside its calls."""
    current = _current_call.get()
    return current.owned_by(module) if current is not None else None


class Module:
    """Base class discovering declarations and child modules assigned in ``__init__``.

    Subclasses call ``super().__init__()`` first, then assign declarations and children in the
    documented section order. ``name`` is the snake_case class name; ``path`` is the dotted
    position in the tree, or the name for a standalone module.
    """

    stateful = False
    repr_fields = ()

    def __init__(self):
        """Create the ordered registries and the run-owned metadata."""
        for _, registry in _REGISTRIES:
            object.__setattr__(self, registry, {})
        object.__setattr__(self, "_children", {})
        object.__setattr__(self, "_pre_hooks", {})
        object.__setattr__(self, "_hooks", {})
        object.__setattr__(self, "_input_values", {})
        object.__setattr__(self, "_path", "")
        object.__setattr__(self, "_fluid", runtime.get_default_fluid())
        object.__setattr__(self, "bindings", {})
        object.__setattr__(self, "boundary", {})
        object.__setattr__(self, "param_history", [DatedParams(params={})])
        object.__setattr__(self, "_param_overrides", {})

    @property
    def name(self):
        """Return the snake_case class name, for example ``heat_exchanger``."""
        return snake_case(type(self).__name__)

    @property
    def path(self):
        """Return the assigned tree path or standalone derived name."""
        return self._path or self.name

    @property
    def fluid(self):
        """Return the fluid this module's streams carry."""
        return self._fluid

    @fluid.setter
    def fluid(self, value):
        """Set and validate the module fluid; ``state_dict`` saves it."""
        object.__setattr__(self, "_fluid", Fluid.model_validate(value))

    def __setattr__(self, name, value):
        """Register declarations and children, or assign declared values."""
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        if "_parameters" not in self.__dict__:
            if isinstance(value, (Declaration, Module)):
                raise DeclarationError(
                    f"{type(self).__name__}.__init__ must call super().__init__() before "
                    f"assigning {name!r}"
                )
            object.__setattr__(self, name, value)
            return
        if isinstance(value, Declaration):
            self._register_declaration(name, value)
        elif isinstance(value, Module):
            self.add_module(name, value)
        else:
            self._assign_value(name, value)

    def _register_declaration(self, name, declaration):
        existing = self._declarations().get(name)
        if existing is not None and existing is not declaration:
            raise DeclarationError(f"{self.path}.{name}: declaration is already registered")
        registry = next(
            getattr(self, registry)
            for kind, registry in _REGISTRIES
            if isinstance(declaration, kind)
        )
        registry[name] = declaration.bind(self, name)
        if isinstance(declaration, Parameter) and declaration.initialized:
            initial = self.param_history[0].params
            initial[name] = to_jsonable_python(deepcopy(declaration.value))

    def _assign_value(self, name, value):
        if name in self._parameters:
            self._parameters[name].set(value)
            return
        inputs = self._controls | self._boundaries
        if name in inputs:
            self._set_input(name, inputs[name].validate(value))
            return
        if name in self._outputs:
            self._record_output(name, value)
            return
        if name in self._declarations():
            raise DeclarationError(f"{self.path}.{name}: cannot replace a declaration")
        self._children.pop(name, None)
        object.__setattr__(self, name, value)

    def _set_input(self, name, value):
        call = _active_call(self)
        target = call.inputs if call is not None else self._input_values
        target[name] = value

    def _record_output(self, name, value):
        call = _active_call(self)
        if call is None or call.outputs is None:
            raise OutputError(
                f"{self.path}.{name}: outputs may only be assigned while computing outputs"
            )
        call.outputs[name] = self._outputs[name].validate(value)

    def add_module(self, name, module):
        """Register an immediate child and reject ambiguous names or ownership cycles."""
        if not isinstance(module, Module):
            raise DeclarationError(f"{self.path}.{name}: child must be a Module")
        if not name or "." in name or name.startswith("_"):
            raise DeclarationError(f"{self.path}: invalid child name {name!r}")
        if name in self._declarations():
            raise DeclarationError(f"{self.path}: child name {name!r} conflicts with a declaration")
        if hasattr(type(self), name):
            raise DeclarationError(f"{self.path}: child name {name!r} shadows a module attribute")
        if any(item is self for item in module.modules()):
            raise DeclarationError(f"{self.path}.{name}: module ownership cannot contain a cycle")
        self._children[name] = module
        object.__setattr__(self, name, module)
        module._set_path(join_path(self._path, name))

    def _set_path(self, path):
        object.__setattr__(self, "_path", path)
        for declaration in self._declarations().values():
            declaration.bind(self, declaration.name)
        for name, child in self.named_children():
            child._set_path(join_path(path, name))

    def _declarations(self):
        result = {}
        for _, registry in _REGISTRIES:
            result.update(getattr(self, registry))
        return result

    def __getattr__(self, name):
        """Resolve parameter values, current input and output values and port declarations.

        Called only for names that are not ordinary attributes. Controls and boundaries resolve
        to the value of the running call, then the persisted value, then the declared default.
        Outputs resolve to the value recorded in the running call, otherwise to their
        declaration, as do inlets and outlets.
        """
        registries = self.__dict__
        if name in registries.get("_parameters", {}):
            return self._parameter_value(name)
        if name in registries.get("_controls", {}) or name in registries.get("_boundaries", {}):
            return self._input_value(name)
        if name in registries.get("_outputs", {}):
            call = _active_call(self)
            if call is not None and call.outputs is not None and name in call.outputs:
                return call.outputs[name]
            return self._outputs[name]
        for registry in ("_inlets", "_outlets"):
            if name in registries.get(registry, {}):
                return registries[registry][name]
        raise AttributeError(name)

    def _parameter_value(self, name):
        parameter = self._parameters[name]
        if not parameter.initialized:
            raise MissingValueError(f"{parameter.path}: parameter is uninitialized")
        return parameter.value

    def _input_value(self, name):
        call = _active_call(self)
        if call is not None and name in call.inputs:
            return call.inputs[name]
        if name in self._input_values:
            return self._input_values[name]
        declaration = (self._controls | self._boundaries)[name]
        if declaration.default is not UNSET:
            return declaration.validate(deepcopy(declaration.default))
        raise MissingValueError(
            f"{declaration.path}: {declaration.section} {name!r} has no value "
            f"[{declaration.unit or '-'}]"
        )

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
                yield from walk(child, join_path(path, name))

        yield from walk(self, prefix)

    def modules(self):
        """Walk self and all unique descendants."""
        for _, module in self.named_modules():
            yield module

    def get_submodule(self, path):
        """Resolve a dotted descendant path; the empty path denotes self."""
        module = self._find_submodule(path)
        if module is None:
            raise UnknownNameError(
                f"{self.path}: unknown module path {path!r}"
                f"{did_you_mean(path, dict(self.named_modules()))}"
            )
        return module

    def _find_submodule(self, path):
        """Return the descendant at a dotted path, or ``None`` when there is none."""
        module = self
        for part in path.split(".") if path else ():
            module = module._children.get(part)
            if module is None:
                return None
        return module

    @property
    def is_leaf(self):
        """Whether this module owns no child modules."""
        return not self._children

    def _named(self, registry_name, recurse):
        for path, module in self.named_modules() if recurse else [("", self)]:
            for name, declaration in getattr(module, registry_name).items():
                yield join_path(path, name), declaration

    def _section(self, registry_name, recurse):
        return dict(self._named(registry_name, recurse))

    def parameters(self, recurse=True):
        """Iterate parameter declarations of this module and, by default, its descendants."""
        for _, parameter in self._named("_parameters", recurse):
            yield parameter

    def named_parameters(self, recurse=True):
        """Iterate ``(dotted path, parameter)`` pairs relative to this module."""
        yield from self._named("_parameters", recurse)

    def calibratable_parameters(self, recurse=True):
        """Return only parameters explicitly marked calibratable."""
        return [p for p in self.parameters(recurse) if p.calibratable]

    def controls(self, recurse=True):
        """Return controllable input declarations by dotted path relative to this module."""
        return self._section("_controls", recurse)

    def boundaries(self, recurse=True):
        """Return external boundary declarations by dotted path relative to this module."""
        return self._section("_boundaries", recurse)

    def inputs(self, recurse=True):
        """Return controls followed by boundaries, by dotted path relative to this module."""
        return self.controls(recurse) | self.boundaries(recurse)

    def outputs(self, recurse=True):
        """Return computed output declarations by dotted path relative to this module."""
        return self._section("_outputs", recurse)

    def soft_sensors(self, recurse=True):
        """Return outputs marked as inferred measurements, by dotted path."""
        return {name: value for name, value in self.outputs(recurse).items() if value.soft_sensor}

    def inlets(self):
        """Return this module's own inlet declarations; a child's ports are internal wiring."""
        return dict(self._inlets)

    def outlets(self):
        """Return this module's own outlet declarations; a child's ports are internal wiring."""
        return dict(self._outlets)

    def _get_declaration(self, path, registry_name, kind):
        module_path, name = split_path(path)
        module = self.get_submodule(module_path)
        registry = getattr(module, registry_name)
        if name not in registry:
            raise UnknownNameError(
                f"{self.path}: unknown {kind} {path!r}{did_you_mean(name, registry)}; "
                f"valid: {join_names(registry)}"
            )
        return registry[name]

    def get_parameter(self, path):
        """Return parameter metadata by local or dotted path."""
        return self._get_declaration(path, "_parameters", "parameter")

    def get_control(self, path):
        """Return control metadata by local or dotted path."""
        return self._get_declaration(path, "_controls", "control")

    def get_boundary(self, path):
        """Return boundary metadata by local or dotted path."""
        return self._get_declaration(path, "_boundaries", "boundary")

    def set_inputs(self, mapping):
        """Persist validated controls and boundaries addressed by relative dotted path."""
        declarations = self.inputs()
        pending = []
        for path, value in mapping.items():
            if path not in declarations:
                raise UnknownNameError(
                    f"{self.path}: unknown control/boundary path {path!r}"
                    f"{did_you_mean(path, declarations)}; valid: {join_names(declarations)}"
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

    def update_params(self, **changes):
        """Set validated parameters, addressed by local or dotted path, as explicit overrides.

        Returns the module, so ``ESP().update_params(no_stages=12)`` builds a configured module.
        """
        for name, value in changes.items():
            self.get_parameter(name).set(value)
        return self

    def params_at(self, at):
        """Return the complete validated parameter mapping active at an instant.

        ``at=None`` selects the latest snapshot. Explicit overrides win over every snapshot.
        """
        eligible = [
            item
            for item in self.param_history
            if at is None or item.valid_from is None or item.valid_from <= to_utc(at)
        ]
        if not eligible:
            raise ConfigurationError(f"{self.path}: no parameters valid at {at}")
        selected = max(eligible, key=lambda item: item.valid_from or _EARLIEST)
        values = selected.params | self._param_overrides
        return {name: self._parameters[name].validate(value) for name, value in values.items()}

    def clear_param_overrides(self):
        """Forget explicit overrides, so values come from the dated snapshots alone."""
        self._param_overrides = {}

    def has_input_value(self, name):
        """Return whether control or boundary ``name`` has a persisted value."""
        return name in self._input_values

    def _latest_snapshot_date(self):
        """Return the newest snapshot date as ISO text, or ``None`` for undated designs.

        Plant files store it as ``active_from``; loading ignores it because the snapshots
        already contain it.
        """
        dates = [item.valid_from for item in self.param_history if item.valid_from is not None]
        return max(dates).isoformat() if dates else None

    def apply_params_at(self, at):
        """Apply dated parameter snapshots recursively while retaining explicit overrides."""
        for module in self.modules():
            for name, value in module.params_at(at).items():
                module._parameters[name].set(value, explicit=False)

    def forward(self, inlets):
        """Move inlet fluids to declared outlets; subclasses implement this."""
        raise NotImplementedError(f"{type(self).__name__} has no forward method")

    def _compute_outputs(self, inlets, outlets):
        """Compute leaf outputs after ``forward``; overrides never call ``super()``."""

    def __call__(self, *args, **kwargs):
        """Apply controls and boundaries, run hooks and ``forward``, and validate outlets."""
        missing = self.missing_parameters()
        if missing:
            raise MissingValueError(f"{self.path}: uninitialized parameters: {', '.join(missing)}")
        self._resolve_formula_outputs()
        inlets, supplied = self._split_call_args(args, kwargs)
        parent = _current_call.get()
        call = _Call(
            module=self,
            inputs=self._resolve_inputs(supplied),
            outputs={} if outputs_enabled() else None,
            parent=parent,
        )
        token = _current_call.set(call)
        try:
            outlets = self._evaluate(inlets, call)
        finally:
            _current_call.reset(token)
        result = ModuleResult(
            outputs=Values(call.outputs or {}, self._outputs),
            outlets=outlets,
            inlets=inlets,
            inputs=dict(call.inputs),
            children=dict(call.call_records),
            call_records=tuple(call.call_records),
            is_leaf=self.is_leaf,
        )
        if parent is not None:
            parent.call_records.append((self._relative_path(parent.module), result))
        return result

    def _evaluate(self, inlets, call):
        """Run pre-hooks, ``forward``, output computation and forward hooks of one call."""
        for hook in tuple(self._pre_hooks.values()):
            hook(self, inlets)
        outlets = self._check_outlets(self.forward(inlets))
        if call.outputs is None:
            return outlets
        self._compute_outputs(inlets, outlets)
        self._compute_formula_outputs(call.call_records)
        for hook in tuple(self._hooks.values()):
            hook(self, inlets, outlets)
        self._check_outputs(call.outputs)
        return outlets

    def _relative_path(self, owner):
        prefix = owner._path + "." if owner._path else ""
        return self._path.removeprefix(prefix) or self.name

    def _split_call_args(self, args, kwargs):
        """Return validated inlet ``Ports`` and the supplied control/boundary keywords."""
        inlet_names = list(self._inlets)
        valid_names = inlet_names + list(self._controls) + list(self._boundaries)
        self._check_keywords(kwargs, valid_names)
        if len(args) == 1 and isinstance(args[0], Mapping):
            inlet_values = self._mapping_inlets(args[0], kwargs)
        else:
            inlet_values = self._positional_inlets(args, kwargs)
        missing = [name for name in inlet_names if name not in inlet_values]
        if missing:
            raise CallError(
                f"{self.path}: missing required inlet(s) {', '.join(missing)}; "
                f"valid names: {join_names(inlet_names)}"
            )
        inlets = Ports(self._validated_inlets(inlet_values), path=self.path)
        inputs = {
            name: kwargs[name] for name in self._controls | self._boundaries if name in kwargs
        }
        return inlets, inputs

    def _check_keywords(self, kwargs, valid_names):
        unknown = [name for name in kwargs if name not in valid_names]
        if unknown:
            name = unknown[0]
            raise CallError(
                f"{self.path}: unexpected keyword {name!r}{did_you_mean(name, valid_names)}; "
                f"valid names: {join_names(valid_names)}"
            )

    def _mapping_inlets(self, mapping, kwargs):
        valid = join_names(self._inlets)
        mixed = [name for name in self._inlets if name in kwargs]
        if mixed:
            raise CallError(
                f"{self.path}: cannot mix inlet mapping with inlet keyword {mixed[0]!r}; "
                f"valid names: {valid}"
            )
        unknown = [name for name in mapping if name not in self._inlets]
        if unknown:
            name = unknown[0]
            raise CallError(
                f"{self.path}: unknown inlet {name!r}{did_you_mean(name, self._inlets)}; "
                f"valid names: {valid}"
            )
        return mapping

    def _positional_inlets(self, args, kwargs):
        inlet_names = list(self._inlets)
        valid = join_names(inlet_names)
        if len(args) > len(inlet_names):
            raise CallError(
                f"{self.path}: expected at most {len(inlet_names)} positional inlet arguments, "
                f"got {len(args)}; valid names: {valid}"
            )
        values = dict(zip(inlet_names, args))
        duplicate = values.keys() & kwargs.keys()
        if duplicate:
            raise CallError(
                f"{self.path}: multiple values for inlet {next(iter(duplicate))!r}; "
                f"valid names: {valid}"
            )
        values.update({name: kwargs[name] for name in inlet_names if name in kwargs})
        return values

    def _validated_inlets(self, values):
        validated = []
        for name, declaration in self._inlets.items():
            try:
                validated.append((name, declaration.validate(values[name])))
            except (TypeError, ValueError) as exc:
                raise CallError(
                    f"{self.path}: invalid inlet {name!r}; "
                    f"valid names: {join_names(self._inlets)}: {exc}"
                ) from exc
        return validated

    def _check_outlets(self, returned):
        if not isinstance(returned, dict):
            raise OutletError(f"{self.path}: forward must return an outlet dict")
        missing = self._outlets.keys() - returned.keys()
        extra = returned.keys() - self._outlets.keys()
        if missing or extra:
            raise OutletError(
                f"{self.path}: outlet names missing={sorted(missing)}, extra={sorted(extra)}; "
                f"valid names: {join_names(self._outlets)}"
            )
        validated = []
        for name, declaration in self._outlets.items():
            try:
                validated.append((name, declaration.validate(returned[name])))
            except (TypeError, ValueError) as exc:
                raise OutletError(
                    f"{self.path}: invalid outlet {name!r}; "
                    f"valid names: {join_names(self._outlets)}: {exc}"
                ) from exc
        return Ports(validated, path=self.path)

    def _resolve_inputs(self, supplied):
        """Return validated controls and boundaries: supplied, persisted, then default values."""
        resolved = {}
        for name, declaration in (self._controls | self._boundaries).items():
            if name in supplied:
                value = supplied[name]
            elif name in self._input_values:
                value = self._input_values[name]
            elif declaration.default is not UNSET:
                value = deepcopy(declaration.default)
            else:
                raise MissingValueError(
                    f"{declaration.path}: missing required {declaration.section} "
                    f"{name!r} [{declaration.unit or '-'}]"
                )
            resolved[name] = declaration.validate(value)
        return resolved

    def _formula_candidates(self):
        candidates = []
        for path, module in self.named_modules():
            if not path:
                continue
            candidates.extend(join_path(path, name) for name in module._outputs)
            for name, outlet in module._outlets.items():
                fields = getattr(outlet.kind, "model_fields", {})
                candidates.extend(f"{path}.{name}.{field}" for field in fields)
        return candidates

    def _split_formula_target(self, target):
        """Split ``a.b.c`` into the longest descendant module path and the remaining names."""
        parts = target.split(".")
        for size in range(len(parts) - 1, 0, -1):
            module_path = ".".join(parts[:size])
            module = self._find_submodule(module_path)
            if module is not None:
                return module, module_path, parts[size:]
        return None, "", []

    def _resolve_of(self, target):
        module, module_path, remainder = self._split_formula_target(target)
        if module is not None and len(remainder) == 1 and remainder[0] in module._outputs:
            return module_path, ("output", remainder[0], None), module._outputs[remainder[0]]
        if module is not None and len(remainder) == 2 and remainder[0] in module._outlets:
            outlet = module._outlets[remainder[0]]
            field_info = getattr(outlet.kind, "model_fields", {}).get(remainder[1])
            if field_info is not None:
                access = ("outlet", remainder[0], remainder[1])
                return module_path, access, Output(field_info.annotation)
        raise FormulaError(
            f"{self.path}: unknown output formula path {target!r}"
            f"{did_you_mean(target, self._formula_candidates())}"
        )

    def _resolve_formula_outputs(self):
        """Check every formula output once and remember how to compute it."""
        seen = set()
        for name, output in self._outputs.items():
            if output.formula is not None and output._resolved_formula is None:
                resolved, declaration = self._resolve_formula(name, output, seen)
                if declaration is not None:
                    output.infer_kind(declaration)
                output._resolved_formula = resolved
            seen.add(name)

    def _resolve_formula(self, name, output, seen):
        """Return the resolved formula and the declaration whose kind the output takes."""
        kind, *arguments = output.formula
        if kind == "of":
            module_path, access, declaration = self._resolve_of(arguments[0])
            return (kind, module_path, access), declaration
        if kind == "total":
            return (kind, arguments[0]), self._resolve_total(name, arguments[0])
        for reference in arguments:
            if reference not in seen:
                raise FormulaError(
                    f"{self.path}.{name}: ratio references unavailable earlier output "
                    f"{reference!r}{did_you_mean(reference, seen)}"
                )
        return (kind, *arguments), None

    def _descendant_leaves(self):
        """Return every leaf module below this one."""
        return [module for path, module in self.named_modules() if path and module.is_leaf]

    def _resolve_total(self, name, target):
        """Return the declaration that ``Output.total(target)`` sums, after checking it."""
        leaves = self._descendant_leaves()
        declarations = [leaf._outputs[target] for leaf in leaves if target in leaf._outputs]
        if not declarations:
            names = sorted({output for leaf in leaves for output in leaf._outputs})
            raise FormulaError(
                f"{self.path}: no descendant leaf declares output {target!r}"
                f"{did_you_mean(target, names)}"
            )
        found = {declaration.unit for declaration in declarations}
        if len(found) != 1:
            raise FormulaError(
                f"{self.path}.{name}: Output.total({target!r}) has differing units "
                f"{sorted(str(unit) for unit in found)}"
            )
        if any(declaration.quantity not in _ADDITIVE_QUANTITIES for declaration in declarations):
            raise FormulaError(
                f"{self.path}.{name}: Output.total({target!r}) requires an additive "
                "power or mass-flow quantity"
            )
        return declarations[0]

    @staticmethod
    def _recorded_calls(call_records, prefix=""):
        for path, result in call_records:
            full_path = join_path(prefix, path)
            yield full_path, result
            yield from Module._recorded_calls(result.call_records, full_path)

    def _compute_formula_outputs(self, call_records):
        calls = list(self._recorded_calls(call_records))
        for name, output in self._outputs.items():
            if output.formula is None:
                continue
            kind, *arguments = output._resolved_formula
            if kind == "of":
                setattr(self, name, self._output_of(name, calls, *arguments))
            elif kind == "total":
                setattr(self, name, self._output_total(calls, *arguments))
            else:
                setattr(self, name, self._output_ratio(*arguments))

    def _output_of(self, name, calls, module_path, access):
        section, port, field_name = access
        matches = [result for path, result in calls if path == module_path]
        if len(matches) != 1:
            raise OutputError(
                f"{self.path}.{name}: descendant {module_path!r} was called "
                f"{len(matches)} times; expected exactly once"
            )
        values = matches[0].outputs if section == "output" else matches[0].outlets
        value = values[port]
        return getattr(value, field_name) if field_name is not None else value

    @staticmethod
    def _output_total(calls, target):
        return sum(
            result.outputs[target]
            for _, result in calls
            if result.is_leaf and target in result.outputs
        )

    def _output_ratio(self, numerator, denominator):
        """Divide two earlier outputs; ``None`` when either is ``None`` or the divisor is zero."""
        top, bottom = getattr(self, numerator), getattr(self, denominator)
        if top is None or bottom is None or bottom == 0:
            return None
        return top / bottom

    def _check_outputs(self, recorded):
        missing = sorted(self._outputs.keys() - recorded.keys())
        if missing:
            raise OutputError(f"{self.path}: outputs left unassigned: {missing}")

    def initial_state(self):
        """Return independent states for stateful descendants, or None for a leaf."""
        states = {
            name: child.initial_state()
            for name, child in self.named_children()
            if child.stateful or child._children
        }
        return states or None

    def step(self, state, dt, inlets):
        """Evaluate a stateless step; stateful equipment overrides this method.

        A stateless composite cannot integrate stateful descendants, so it refuses them rather
        than returning their state unchanged.
        """
        if dt <= 0:
            raise ValueError("dt must be positive [s]")
        stateful = [path for path, module in self.named_modules() if path and module.stateful]
        if stateful:
            raise ConfigurationError(
                f"{self.path}: stateful descendants {', '.join(stateful)} need a step method "
                "on this composite that steps them"
            )
        return state, self(inlets)

    def register_forward_pre_hook(self, fn):
        """Call ``fn(module, inlets)`` before each forward evaluation."""
        self._check_hook_signature(fn, ("module", "inlets"), "forward pre-hook")
        return RemovableHandle(self._pre_hooks, fn)

    def register_forward_hook(self, fn):
        """Call ``fn(module, inlets, outlets)`` after output computation."""
        self._check_hook_signature(fn, ("module", "inlets", "outlets"), "forward hook")
        return RemovableHandle(self._hooks, fn)

    def _check_hook_signature(self, fn, expected, kind):
        if not has_signature(fn, expected):
            actual = tuple(inspect.signature(fn).parameters)
            raise DeclarationError(
                f"{self.path}: {kind} signature must be ({', '.join(expected)}); "
                f"got ({', '.join(actual)})"
            )

    def health(self, result, measured):
        """Compare one call's ``ModuleResult`` with measured outputs; ``None`` means not assessed.

        Equipment with a diagnostic model overrides this; the engine calls it after each replayed
        twin with the bound measurements of that tick.
        """
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
        """Validate snapshots before applying any of them.

        With ``strict`` the snapshot paths must equal the tree's module paths; otherwise only the
        modules named in ``state`` are filled and unknown paths are rejected.
        """
        modules = dict(self.named_modules())
        missing, unexpected = modules.keys() - state.keys(), state.keys() - modules.keys()
        if unexpected or (strict and missing):
            raise PlantFormatError(
                f"{self.path}: state paths differ; missing={missing}, unexpected={unexpected}"
            )
        pending = []
        for path, entry in state.items():
            module = modules[path]
            values = {
                name: module.get_parameter(name).validate(value)
                for name, value in entry["params"].items()
            }
            pending.append((module, values, Fluid.model_validate(entry["fluid"])))
        for module, values, fluid in pending:
            for name, value in values.items():
                module._parameters[name].set(value, explicit=False)
            object.__setattr__(module, "_fluid", fluid)
        return self

    def to_dict(self):
        """Return portable design, histories, bindings and boundary defaults."""
        state = self.state_dict()
        modules = {}
        for path, module in self.named_modules():
            modules[path] = {
                "class": class_path(type(module)),
                "type": module.name,
                "params": state[path]["params"],
                "fluid": module._fluid.model_dump(mode="json"),
                "param_history": [item.model_dump(mode="json") for item in module.param_history],
                "param_overrides": to_jsonable_python(module._param_overrides),
                "active_from": module._latest_snapshot_date(),
                "bindings": {
                    key: value.model_dump(mode="json") for key, value in module.bindings.items()
                },
                "boundary": to_jsonable_python(module.boundary),
            }
        return {"version": 1, "plant_type": class_path(type(self)), "modules": modules}

    @classmethod
    def from_dict(cls, data):
        """Construct the self-building tree, then fill its state and run metadata."""
        if data.get("version") != 1:
            raise PlantFormatError(f"Unsupported plant format version {data.get('version')!r}")
        expected = class_path(cls)
        if data.get("plant_type") != expected:
            raise PlantFormatError(
                f"Stored plant type {data.get('plant_type')!r} does not match {expected!r}"
            )
        root = cls()
        entries = data.get("modules", {})
        modules = dict(root.named_modules())
        if entries.keys() != modules.keys():
            raise PlantFormatError(
                f"Stored module paths differ; missing={modules.keys() - entries.keys()}, "
                f"unexpected={entries.keys() - modules.keys()}"
            )
        root.load_state_dict(
            {
                path: {"params": entry.get("params", {}), "fluid": entry.get("fluid", {})}
                for path, entry in entries.items()
            }
        )
        for path, module in modules.items():
            module._load_run_metadata(entries[path])
        return root

    def _load_run_metadata(self, entry):
        """Restore dated history, overrides, bindings and boundary defaults from a plant file."""
        self.param_history = [
            DatedParams.model_validate(item) for item in entry.get("param_history", [])
        ] or [DatedParams(params=entry.get("params", {}))]
        self._param_overrides = dict(entry.get("param_overrides", {}))
        self.bindings = {
            key: ModuleBindings.model_validate(value)
            for key, value in entry.get("bindings", {}).items()
        }
        self.boundary = dict(entry.get("boundary", {}))

    def save(self, path):
        """Save the complete portable module tree as JSON."""
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path):
        """Load a JSON plant file as this exact self-building class."""
        return cls.from_dict(read_json(path))

    def extra_repr(self):
        """Display up to four initialized scalar parameters."""
        parts = []
        for name in self.repr_fields or tuple(self._parameters):
            parameter = self._parameters.get(name)
            if parameter is None or not parameter.initialized:
                continue
            value = parameter.value
            if isinstance(value, (dict, list, tuple)) or value is None:
                continue
            parts.append(f"{name}={_display(value, parameter.unit or '', parameter.quantity)}")
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
        """Return the class description and its declarations for interactive use."""
        lines = [first_paragraph(inspect.getdoc(cls) or cls.__name__)]
        module = cls()
        for title, registry in (
            ("Parameters", module._parameters),
            ("Inlets", module._inlets),
            ("Controls", module._controls),
            ("Boundaries", module._boundaries),
            ("Outputs", module._outputs),
            ("Outlets", module._outlets),
        ):
            if registry:
                lines.append(f"\n{title}:")
                lines.extend(f"  {name}: {_describe(value)}" for name, value in registry.items())
        return "\n".join(lines)


def _display(value, unit, quantity):
    """Format one parameter value with its unit, in field units when the runtime asks for them."""
    if runtime.get_display_units() == "field" and unit in _FIELD_DISPLAY_UNITS:
        target = _FIELD_DISPLAY_UNITS[unit]
        value, unit = units.convert(value, unit, target, quantity), target
    shown = f"{value:.5g}" if isinstance(value, float) else str(value)
    return shown + (f" {unit}" if unit and unit != "-" else "")


def _describe(declaration):
    """Return the unit, default and flags of one declaration for ``Module.help``."""
    details = [declaration.unit] if declaration.unit else []
    if isinstance(declaration, Parameter) and declaration.default is not UNSET:
        details.append(f"default={declaration.default!r}")
    if isinstance(declaration, Parameter) and declaration.calibratable:
        details.append("calibratable")
    if isinstance(declaration, Output) and declaration.soft_sensor:
        details.append("soft sensor")
    return ", ".join(details)
