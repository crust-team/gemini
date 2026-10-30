"""Equipment modules: declarations and children registered in ``__init__``, called with inlets.

A module registers what ``__init__`` assigns: ``Parameter``, ``Inlet``, ``Control``, ``Boundary``,
``State``, ``Output`` and ``Outlet`` declarations go to ordered registries and ``Module`` values
become children with dotted paths. Calling a module validates the inlets, applies controls and
boundaries, runs the forward pre-hooks, ``forward``, the leaf ``_compute_outputs`` or composite
output formulas and the forward hooks, then returns a ``ModuleResult``.

The values of one call (resolved controls and boundaries, recorded outputs and the results of
child calls) live in a ``_Call`` record held in the ``_current_call`` context variable while the
call runs; it is the only per-call state. During ``Module.step`` every call record also carries
the ``_Step`` record with the time step and the state trees. ``no_outputs()`` is the only other
context setting.
"""

import importlib
import inspect
from collections.abc import Mapping
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial

import numpy as np
from pydantic_core import to_jsonable_python

from gemini import backends, ops
from gemini.backends import runtime
from gemini.errors import DefinitionError, PhysicsError, ValidationError
from gemini.errors.lookup import UnknownMember
from gemini.modules import description, design, serialization
from gemini.physics import units
from gemini.types.bindings import DatedParams
from gemini.types.declarations import (
    UNSET,
    Boundary,
    Control,
    Declaration,
    Inlet,
    Outlet,
    Output,
    Parameter,
    PortField,
    State,
)
from gemini.types.flows import Stream
from gemini.types.fluid import Fluid
from gemini.types.ports import Ports
from gemini.types.results import ModuleResult
from gemini.utils.context import ContextSetting
from gemini.utils.files import read_json, write_json
from gemini.utils.hooks import RemovableHandle, has_signature
from gemini.utils.mappings import get_nested, set_nested
from gemini.utils.strings import (
    did_you_mean,
    first_paragraph,
    join_names,
    join_path,
    snake_case,
    split_path,
)

_current_call = ContextVar("module_call", default=None)
_outputs_enabled = ContextVar("module_outputs_enabled", default=True)
_FIELD_DISPLAY_UNITS = {"Pa": "bar", "K": "°C", "m3/s": "m3/h", "W": "kW"}
_REGISTRIES = (
    (Parameter, "_parameters"),
    (Inlet, "_inlets"),
    (Control, "_controls"),
    (Boundary, "_boundaries"),
    (State, "_states"),
    (Output, "_outputs"),
    (Outlet, "_outlets"),
)


def _describe_unknown_member(name, module):
    """Name the module path and the closest child, declaration or port for a missing attribute.

    Reads only the instance dictionary, so it also works before ``super().__init__()``.
    """
    registries = module.__dict__
    candidates = list(registries.get("_children", ()))
    for _, registry in _REGISTRIES:
        candidates.extend(registries.get(registry, ()))
    path = registries.get("_path") or module.name
    return f"{path}: unknown member {name!r}{did_you_mean(name, candidates)}"


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
        raise ValidationError(f"Serialized class {path!r} is not a Module", code="invalid_format")
    return value


@dataclass
class _Step:
    """Time step and state trees of one ``Module.step`` in progress.

    ``states`` holds the states at the start of the step and ``next_states`` the states at its
    end, both nested by child name below the stepped module ``root``. ``next_states`` starts as a
    copy of ``states``, so a stateful module that is not called keeps its state.
    """

    root: "Module"
    dt: float
    states: dict
    next_states: dict
    advanced: set = field(default_factory=set)

    def start(self, keys):
        """Return the start-of-step states of the module at ``keys``, or an empty mapping."""
        return deepcopy(get_nested(self.states, keys, None) or {})

    def advance(self, keys, values):
        """Record the end-of-step states of the module at ``keys``; each module advances once."""
        if keys in self.advanced:
            path = ".".join(keys) or self.root.path
            raise ValidationError(
                f"{path}: stateful module called more than once in one step", code="invalid_design"
            )
        self.advanced.add(keys)
        if not keys:
            self.next_states = values
            return
        set_nested(self.next_states, keys, values)


class _ScalarParameters(dict):
    """Parameter values of an eager call as the scope gives them, wrapped on first read."""

    def __init__(self, module):
        """Read parameters of ``module``."""
        super().__init__()
        self._module = module

    def __missing__(self, name):
        """Return the stored value of parameter ``name`` wrapped, and keep it for this call."""
        value = self[name] = ops.scope.wrap(self._module._parameter_value(name))
        return value


def _has_arrays(inlets, inputs):
    """Return whether a call holds arrays over rows, which leaves its scope unwrapped.

    A 0-d array is a scalar: ops give one under a forced NumPy backend.
    """
    for stream in inlets.values():
        for value in (stream.m_dot, stream.T, stream.p):
            if isinstance(value, np.ndarray) and value.ndim:
                return True
    return any(isinstance(value, np.ndarray) and value.ndim for value in inputs.values())


def _numpy_ports(inlets):
    """Return ``inlets`` with stream fields as ``np.float64`` for the eager scope."""
    return Ports._trusted({name: stream._numpy() for name, stream in inlets.items()}, inlets._path)


def _read(call, value):
    """Return a recorded output as the call's physics sees it: wrapped in a wrapping call."""
    if not call.wrapping:
        return value
    return np.float64(value) if type(value) is float else ops.scope.wrap(value)


def _restored(returned, scoped, inlets):
    """Return the outlets of ``forward`` with a passed-through scoped inlet restored."""
    if scoped is inlets or not isinstance(returned, dict):
        return returned
    originals = {id(scoped[name]): inlets[name] for name in inlets}
    return {name: originals.get(id(value), value) for name, value in returned.items()}


def _plain_outlet(value):
    """Return an outlet stream with plain scalar fields; a ``Failed`` field raises its error."""
    return value._plain() if isinstance(value, Stream) else value


@dataclass
class _Call:
    """Values of one module call in progress.

    ``outputs`` is ``None`` when outputs are disabled. ``call_records`` collects the results of
    every child call made during this call, in call order. ``parent`` is the enclosing call.
    ``states`` holds the module's own state values and ``step`` the running ``_Step``, if any.
    A traced call (``gemini.graph``) sets ``parameters`` to the traced parameter values that
    replace the stored ones, and records outputs without validating them. ``trace`` is the
    running trace of ``gemini.graph``: a call made while it is set is recorded in the graph
    through ``trace.child`` instead of being evaluated. ``wrapping`` marks an eager call whose
    physics gets NumPy scalars (``gemini.ops.scope``).
    """

    module: "Module"
    inputs: dict
    outputs: dict | None
    parent: "_Call | None"
    states: dict | None = None
    step: _Step | None = None
    call_records: list = field(default_factory=list)
    parameters: dict | None = None
    trace: object | None = None
    wrapping: bool = False

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


class _ClassOrInstance:
    """Method that runs on the instance, or on a new instance when called on the class.

    ``on_class`` holds the keywords of a call on the class, where no values are stored.
    """

    def __init__(self, function, **on_class):
        """Wrap ``function(module, ...)``."""
        self.function = function
        self.on_class = on_class
        self.__doc__ = function.__doc__

    def __get__(self, instance, owner):
        """Bind to ``instance``, or to a new ``owner()``."""
        if instance is not None:
            return partial(self.function, instance)
        return partial(self.function, owner(), **self.on_class)


class _FolderCategory:
    """The ``category`` of a class: the folder of this package that holds its file.

    ``gemini/modules/pumps/esp.py`` gives ``pumps``, so a shipped class never declares it. A
    class from outside has no such folder and is ``None`` until it assigns ``category`` itself,
    which replaces this descriptor; a subclass of a shipped class states its own too.
    """

    def __get__(self, instance, owner):
        """Return the folder of ``owner``, or ``None`` for a file outside the folders."""
        if not owner.__module__.startswith(f"{__package__}."):
            return None
        folder, _, file = owner.__module__.removeprefix(f"{__package__}.").partition(".")
        return folder if file else None


class Module:
    """Base class discovering declarations and child modules assigned in ``__init__``.

    Subclasses call ``super().__init__()`` first, then assign declarations and children in the
    documented section order. ``name`` is the snake_case class name; ``path`` is the dotted
    position in the tree, or the name for a standalone module; ``category`` is the folder of the
    class.
    """

    repr_fields = ()
    category = _FolderCategory()
    describe = _ClassOrInstance(description.describe, values=False)
    parameter_schema = _ClassOrInstance(description.parameter_schema)
    validate_params = _ClassOrInstance(description.validate_params)

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
        object.__setattr__(self, "_param_history", [DatedParams(params={})])
        object.__setattr__(self, "_param_overrides", {})
        object.__setattr__(self, "_derived_params", set())
        object.__setattr__(self, "_stated_child_params", set())
        object.__setattr__(self, "_graph_cache", None)

    @property
    def name(self):
        """Return the snake_case class name, for example ``heat_exchanger``."""
        return snake_case(type(self).__name__)

    @property
    def _type_label(self):
        """Return the name ``repr`` shows for this module."""
        return type(self).__name__

    @property
    def path(self):
        """Return the assigned tree path or standalone derived name."""
        return self._path or self.name

    @property
    def stateful(self):
        """Whether the module declares states that ``step`` advances."""
        return bool(self._states)

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
                raise DefinitionError(
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
            raise DefinitionError(f"{self.path}.{name}: declaration is already registered")
        registry = next(
            getattr(self, registry)
            for kind, registry in _REGISTRIES
            if isinstance(declaration, kind)
        )
        if isinstance(declaration, Output) and declaration.formula is not None:
            self._check_formula_references(name, declaration.formula)
        registry[name] = declaration.bind(self, name)
        if isinstance(declaration, Parameter) and declaration.initialized:
            initial = self._param_history[0].params
            initial[name] = to_jsonable_python(deepcopy(declaration.value))

    def _check_formula_references(self, name, formula):
        """Reject a formula whose declaration references do not belong to this module tree.

        ``Output.of`` must reference an output or outlet field of a descendant and
        ``Output.ratio`` two earlier outputs of this module, so a wrong reference fails while
        the class is built.
        """
        kind, *references = formula
        if kind == "of":
            self._check_of_target(name, references[0])
        if kind == "ratio":
            self._check_ratio_operands(name, references)

    def _check_of_target(self, name, target):
        if not isinstance(target, (Output, PortField)):
            raise DefinitionError(
                f"{self.path}.{name}: Output.of target = {target!r}; expected a descendant output "
                "declaration or an outlet field reference such as self.child.outlet.field('T')"
            )
        owner = target.port.owner if isinstance(target, PortField) else target.owner
        if owner is None or owner is self or self._descendant_path(owner) is None:
            raise DefinitionError(
                f"{self.path}.{name}: Output.of target {target.path} is not an output or "
                "outlet field of a descendant module"
            )

    def _check_ratio_operands(self, name, operands):
        for operand in operands:
            if not isinstance(operand, Output) or self._outputs.get(operand.name) is not operand:
                described = operand.path if isinstance(operand, Output) else repr(operand)
                raise DefinitionError(
                    f"{self.path}.{name}: Output.ratio operand {described} is not an "
                    f"earlier output of this module; valid: {join_names(self._outputs)}"
                )

    def _descendant_path(self, module):
        """Return the dotted path of ``module`` below this one, or ``None`` outside the tree."""
        return next((path for path, item in self.named_modules() if item is module), None)

    def _assign_value(self, name, value):
        if name in self._parameters:
            self._parameters[name].owner._set_parameter(name, value)
            return
        inputs = self._controls | self._boundaries
        if name in inputs:
            self._set_input(name, inputs[name].validate(value))
            return
        if name in self._outputs:
            self._record_output(name, value)
            return
        if name in self._states:
            raise DefinitionError(f"{self.path}.{name}: a state changes only in _advance_states")
        if name in self._declarations():
            raise DefinitionError(f"{self.path}.{name}: cannot replace a declaration")
        self._children.pop(name, None)
        object.__setattr__(self, name, value)

    def _set_input(self, name, value):
        call = _active_call(self)
        target = call.inputs if call is not None else self._input_values
        target[name] = value

    def _record_output(self, name, value):
        call = _active_call(self)
        if call is None or call.outputs is None:
            raise DefinitionError(
                f"{self.path}.{name}: outputs may only be assigned while computing outputs"
            )
        if call.trace is not None:
            call.outputs[name] = value
            return
        call.outputs[name] = self._outputs[name].validate(value)

    def add_module(self, name, module):
        """Register an immediate child and reject ambiguous names or ownership cycles."""
        if not isinstance(module, Module):
            raise DefinitionError(f"{self.path}.{name}: child must be a Module")
        if not name or "." in name or name.startswith("_"):
            raise DefinitionError(f"{self.path}: invalid child name {name!r}")
        if name in self._declarations():
            raise DefinitionError(f"{self.path}: child name {name!r} conflicts with a declaration")
        if hasattr(type(self), name):
            raise DefinitionError(f"{self.path}: child name {name!r} shadows a module attribute")
        if any(item is self for item in module.modules()):
            raise DefinitionError(f"{self.path}.{name}: module ownership cannot contain a cycle")
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
        States resolve to the value at the start of the running step, else the initial state.
        Outputs resolve to the value recorded in the running call, otherwise to their
        declaration, as do inlets and outlets.
        """
        registries = self.__dict__
        if name in registries.get("_parameters", {}):
            call = _active_call(self)
            if call is not None and call.parameters is not None:
                return call.parameters[name]
            return self._parameter_value(name)
        if name in registries.get("_controls", {}) or name in registries.get("_boundaries", {}):
            return self._input_value(name)
        if name in registries.get("_states", {}):
            call = _active_call(self)
            if call is not None and call.states is not None:
                return call.states[name]
            return self._initial_states()[name]
        if name in registries.get("_outputs", {}):
            call = _active_call(self)
            if call is not None and call.outputs is not None and name in call.outputs:
                return _read(call, call.outputs[name])
            return self._outputs[name]
        for registry in ("_inlets", "_outlets"):
            if name in registries.get(registry, {}):
                return registries[registry][name]
        raise UnknownMember(name, self, _describe_unknown_member)

    def _parameter_value(self, name):
        parameter = self._parameters[name]
        if not parameter.initialized:
            raise ValidationError(
                f"{parameter.path}: parameter is uninitialized", code="missing_value"
            )
        return parameter.value

    def _input_value(self, name):
        call = _active_call(self)
        if call is not None and name in call.inputs:
            return call.inputs[name]
        if name in self._input_values:
            return self._input_values[name]
        declaration = (self._controls | self._boundaries)[name]
        if declaration.default is not UNSET:
            return declaration.default_value()
        raise ValidationError(
            f"{declaration.path}: {declaration.section} {name!r} has no value "
            f"[{declaration.unit or '-'}]",
            code="missing_value",
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
            raise ValidationError(
                f"{self.path}: unknown module path {path!r}"
                f"{did_you_mean(path, dict(self.named_modules()))}",
                code="unknown_name",
            )
        return module

    get_module = get_submodule

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

    def states(self, recurse=True):
        """Return state declarations by dotted path relative to this module."""
        return self._section("_states", recurse)

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
            raise ValidationError(
                f"{self.path}: unknown {kind} {path!r}; valid: {join_names(registry)}"
                f"{did_you_mean(name, registry)}",
                code="unknown_name",
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
                raise ValidationError(
                    f"{self.path}: unknown control/boundary path {path!r}; valid: "
                    f"{join_names(declarations)}{did_you_mean(path, declarations)}",
                    code="unknown_name",
                )
            declaration = declarations[path]
            pending.append((declaration.owner, declaration.name, declaration.validate(value)))
        for owner, name, value in pending:
            owner._input_values[name] = value
        return self

    def missing_parameters(self):
        """Return dotted paths of all uninitialized parameters."""
        return [name for name, value in self.named_parameters() if not value.initialized]

    def _prepare(self):
        """Reject uninitialized parameters and resolve the formula outputs, before any call."""
        missing = self.missing_parameters()
        if missing:
            raise ValidationError(
                f"{self.path}: uninitialized parameters: {', '.join(missing)}", code="missing_value"
            )
        self._resolve_formula_outputs()

    @property
    def is_initialized(self):
        """Whether every parameter in this module tree has a value."""
        return not self.missing_parameters()

    def update_params(self, **changes):
        """Set validated parameters, addressed by local or dotted path, as explicit overrides.

        Returns the module, so ``ESP().update_params(stage_count=12)`` builds a configured module.
        """
        for name, value in changes.items():
            parameter = self.get_parameter(name)
            parameter.owner._set_parameter(parameter.name, value)
        return self

    def _set_parameter(self, name, value):
        """Set one own parameter as an explicit override; a deriving module derives from it."""
        if self._derives_params():
            self.set_params("", {name: value})
            return
        self._parameters[name].set(value)

    def _derives_params(self):
        """Return whether this class overrides ``set_params`` to derive its children's values."""
        return type(self).set_params is not Module.set_params

    def _own_values(self, params, valid_from=None):
        """Return the own parameters in force at ``valid_from`` with those of ``params``, in SI."""
        given = {name: value for name, value in params.items() if name in self._parameters}
        checked = {name: self._parameters[name].validate(value) for name, value in given.items()}
        return self._params_at(valid_from) | checked

    def _keep_derived(self, derived, params):
        """Return the ``derived`` child values that no explicit value replaces, and record them.

        A deriving ``set_params`` calls this with its derived values and the ``params`` of the
        call. A dotted name in ``params`` is an explicit child value, now and in later calls, and
        so is a child value set through ``update_params``. The names kept are the ones
        ``to_dict`` leaves out.
        """
        self._stated_child_params |= {name for name in params if "." in name}
        kept = {
            name: value
            for name, value in derived.items()
            if name not in self._stated_child_params and not self._is_overridden(name)
        }
        self._derived_params = (self._derived_params | kept.keys()) - self._stated_child_params
        return kept

    def _is_overridden(self, name):
        parameter = design.parameter(self, name)
        return parameter.name in parameter.owner._param_overrides

    def _params_at(self, at):
        """Return the complete validated parameter mapping active at an instant.

        ``at=None`` selects the latest snapshot. Explicit overrides win over every snapshot.
        """
        selected = design.snapshot_at(self, at)
        values = selected.params | self._param_overrides
        return {name: self._parameters[name].validate(value) for name, value in values.items()}

    def clear_param_overrides(self):
        """Forget explicit overrides, so values come from the dated snapshots alone."""
        self._param_overrides = {}

    def has_input_value(self, name):
        """Return whether control or boundary ``name`` has a persisted value."""
        return name in self._input_values

    def apply_params_at(self, at):
        """Apply dated parameter snapshots recursively while retaining explicit overrides."""
        for module in self.modules():
            for name, value in module._params_at(at).items():
                module._parameters[name].set(value, explicit=False)

    def forward(self, inlets):
        """Move inlet fluids to declared outlets; subclasses implement this."""
        raise NotImplementedError(f"{type(self).__name__} has no forward method")

    def _compute_outputs(self, inlets, outlets):
        """Compute leaf outputs after ``forward``; overrides never call ``super()``."""

    def __call__(self, *args, **kwargs):
        """Apply controls and boundaries, run hooks and ``forward``, and validate outlets."""
        parent = _current_call.get()
        return self._run(args, kwargs, parent.step if parent is not None else None)

    def _run(self, args, kwargs, step):
        """Evaluate one call; inside a step a stateful module also advances its states."""
        self._prepare()
        inlets, supplied = self._split_call_args(args, kwargs)
        parent = _current_call.get()
        if parent is not None and parent.trace is not None:
            return parent.trace.child(self, inlets, supplied, parent)
        inputs = self._resolve_inputs(supplied)
        with ops.scope.Scope(self._scalar_mode(), _has_arrays(inlets, inputs)) as scope:
            call = self._eager_call(inputs, parent, step, scope.wrapping)
            token = _current_call.set(call)
            try:
                scoped = _numpy_ports(inlets) if scope.wrapping else inlets
                outlets = self._evaluate(inlets, scoped, call)
                if step is not None and self._states:
                    values = self._next_states(scoped, outlets, step.dt)
                    step.advance(self._step_keys(step), values)
            finally:
                _current_call.reset(token)
        result = ModuleResult.of(
            self,
            call.outputs or {},
            outlets,
            inlets,
            ops.scope.plain(dict(call.inputs)),
            call.call_records,
        )
        if parent is not None:
            parent.call_records.append((self._relative_path(parent.module), result))
        return result

    def _eager_call(self, inputs, parent, step, wrapping):
        """Return the call record of an eager call; ``wrapping`` gives physics NumPy scalars.

        Wrapped controls, boundaries, states and (read on demand) parameters are what ``forward``
        sees, so a plain operator on them is silent like the ops; results hold plain values.
        """
        states = self._call_states(step)
        if wrapping:
            inputs = {name: ops.scope.wrap(value) for name, value in inputs.items()}
            states = None if states is None else ops.scope.wrap(states)
        return _Call(
            module=self,
            inputs=inputs,
            outputs={} if outputs_enabled() else None,
            parent=parent,
            states=states,
            step=step,
            parameters=_ScalarParameters(self) if wrapping else None,
            wrapping=wrapping,
        )

    def _scalar_mode(self):
        """Return ``WRAP`` to give physics NumPy scalars in an eager call, else ``PLAIN``.

        NOTE(refactor): the ESP overrides it for float32 precision, whose arithmetic an
        ``np.float64`` scalar would change; no other module does.
        """
        return backends.WRAP

    def _evaluate(self, inlets, scoped, call):
        """Run pre-hooks, ``forward``, output computation and forward hooks of one call.

        Hooks see the plain ``inlets``; ``forward`` and the outputs see ``scoped``.
        """
        for hook in tuple(self._pre_hooks.values()):
            hook(self, inlets)
        returned = self.forward(scoped)
        if call.trace is None:
            outlets = self._check_outlets(_restored(returned, scoped, inlets))
        else:
            self._check_outlet_names(returned)
            outlets = Ports({name: returned[name] for name in self._outlets}, path=self.path)
        if call.outputs is not None:
            self._output_step(scoped, inlets, outlets, call)
        return outlets

    def _output_step(self, scoped, inlets, outlets, call):
        """Compute the outputs after ``forward``, the one sequence of an eager and a traced call.

        ``_compute_outputs`` and the formula outputs see ``scoped``; forward hooks see the plain
        ``inlets``, in a trace through ``call.trace`` which tells whether they write an output.
        """
        self._compute_outputs(scoped, outlets)
        self._compute_formula_outputs(call)
        for hook in tuple(self._hooks.values()):
            if call.trace is None:
                hook(self, inlets, outlets)
            else:
                call.trace.hook(self, hook, inlets, outlets, call)
        self._check_outputs(call.outputs)

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
            raise ValidationError(
                f"{self.path}: missing required inlet(s) {', '.join(missing)}; "
                f"valid names: {join_names(inlet_names)}",
                code="invalid_call",
            )
        inlets = self._validated_ports(
            "inlet", self._inlets, inlet_values, partial(ValidationError, code="invalid_call")
        )
        inputs = {
            name: kwargs[name] for name in self._controls | self._boundaries if name in kwargs
        }
        return inlets, inputs

    def _check_keywords(self, kwargs, valid_names):
        unknown = [name for name in kwargs if name not in valid_names]
        if unknown:
            name = unknown[0]
            raise ValidationError(
                f"{self.path}: unexpected keyword {name!r}; valid names: {join_names(valid_names)}"
                f"{did_you_mean(name, valid_names)}",
                code="invalid_call",
            )

    def _mapping_inlets(self, mapping, kwargs):
        valid = join_names(self._inlets)
        mixed = [name for name in self._inlets if name in kwargs]
        if mixed:
            raise ValidationError(
                f"{self.path}: cannot mix inlet mapping with inlet keyword {mixed[0]!r}; "
                f"valid names: {valid}",
                code="invalid_call",
            )
        unknown = [name for name in mapping if name not in self._inlets]
        if unknown:
            name = unknown[0]
            raise ValidationError(
                f"{self.path}: unknown inlet {name!r}; valid names: {valid}"
                f"{did_you_mean(name, self._inlets)}",
                code="invalid_call",
            )
        return mapping

    def _positional_inlets(self, args, kwargs):
        inlet_names = list(self._inlets)
        valid = join_names(inlet_names)
        if len(args) > len(inlet_names):
            raise ValidationError(
                f"{self.path}: expected at most {len(inlet_names)} positional inlet arguments, "
                f"got {len(args)}; valid names: {valid}",
                code="invalid_call",
            )
        values = dict(zip(inlet_names, args))
        duplicate = values.keys() & kwargs.keys()
        if duplicate:
            raise ValidationError(
                f"{self.path}: multiple values for inlet {next(iter(duplicate))!r}; "
                f"valid names: {valid}",
                code="invalid_call",
            )
        values.update({name: kwargs[name] for name in inlet_names if name in kwargs})
        return values

    def _validated_ports(self, kind, declarations, values, error, prepare=lambda value: value):
        """Return the ``Ports`` of ``values`` validated by ``declarations``, else raise ``error``.

        ``kind`` is ``"inlet"`` or ``"outlet"`` in the message; ``prepare`` is applied to each value
        before it is validated.
        """
        validated = []
        for name, declaration in declarations.items():
            value = prepare(values[name])
            try:
                validated.append((name, declaration.validate(value)))
            except (TypeError, ValueError, PhysicsError) as exc:
                raise error(
                    f"{self.path}: invalid {kind} {name!r}; "
                    f"valid names: {join_names(declarations)}: {exc}"
                ) from exc
        return Ports(validated, path=self.path)

    def _check_outlet_names(self, returned):
        """Reject a ``forward`` result that is not a dict of exactly the declared outlets."""
        if not isinstance(returned, dict):
            raise DefinitionError(f"{self.path}: forward must return an outlet dict")
        missing = self._outlets.keys() - returned.keys()
        extra = returned.keys() - self._outlets.keys()
        if missing or extra:
            raise DefinitionError(
                f"{self.path}: outlet names missing={sorted(missing)}, extra={sorted(extra)}; "
                f"valid names: {join_names(self._outlets)}"
            )

    def _check_outlets(self, returned):
        self._check_outlet_names(returned)
        return self._validated_ports(
            "outlet", self._outlets, returned, DefinitionError, _plain_outlet
        )

    def _resolve_inputs(self, supplied):
        """Return validated controls and boundaries: supplied, persisted, then default values."""
        return {
            name: (
                declaration.validate(supplied[name])
                if name in supplied
                else self._input_value(name)
            )
            for name, declaration in (self._controls | self._boundaries).items()
        }

    def _resolve_formula_outputs(self):
        """Resolve every formula and automatic-sum output once and remember how to compute it."""
        for name, output in self._outputs.items():
            if output._resolved_formula is not None:
                continue
            if output.formula is not None:
                output._resolved_formula = self._resolve_formula(output.formula)
            elif output.additive and not self.is_leaf:
                self._check_summed(name, output)
                output._resolved_formula = ("sum", name)

    def _resolve_formula(self, formula):
        """Return the descendant path and access of ``Output.of``, or the ratio operand names."""
        kind, *references = formula
        if kind == "ratio":
            return (kind, *(reference.name for reference in references))
        target = references[0]
        if isinstance(target, PortField):
            access = ("outlet", target.port.name, target.name)
            return kind, self._descendant_path(target.port.owner), access
        return kind, self._descendant_path(target.owner), ("output", target.name, None)

    def _descendant_leaves(self):
        """Return every leaf module below this one."""
        return [module for path, module in self.named_modules() if path and module.is_leaf]

    def _check_summed(self, name, output):
        """Check that descendant leaves declare ``name`` with the quantity and unit of ``output``.

        A composite's additive output without a formula is the sum of the descendant leaf
        outputs of the same name; every one must have the same quantity and unit.
        """
        leaves = self._descendant_leaves()
        declarations = [leaf._outputs[name] for leaf in leaves if name in leaf._outputs]
        if not declarations:
            names = sorted({output for leaf in leaves for output in leaf._outputs})
            raise DefinitionError(
                f"{self.path}.{name}: no descendant leaf declares output {name!r} to sum"
                f"{did_you_mean(name, names)}"
            )
        for declaration in declarations:
            if (declaration.quantity, declaration.unit) != (output.quantity, output.unit):
                raise DefinitionError(
                    f"{self.path}.{name}: {declaration.path} = {declaration.quantity} "
                    f"[{declaration.unit}]; expected {output.quantity} [{output.unit}] to sum it"
                )

    @staticmethod
    def _recorded_calls(call_records, prefix=""):
        for path, result in call_records:
            full_path = join_path(prefix, path)
            yield full_path, result
            yield from Module._recorded_calls(result.call_records, full_path)

    def _compute_formula_outputs(self, call):
        """Record formula outputs and automatic sums in declaration order.

        An automatic sum is skipped when the module already recorded its own value.
        """
        calls = list(self._recorded_calls(call.call_records))
        for name, output in self._outputs.items():
            if output._resolved_formula is None:
                continue
            kind, *arguments = output._resolved_formula
            if kind == "of":
                setattr(self, name, self._output_of(name, calls, *arguments))
            elif kind == "sum" and name not in call.outputs:
                setattr(self, name, self._output_sum(calls, *arguments))
            elif kind == "ratio":
                setattr(self, name, self._output_ratio(*arguments))

    def _output_of(self, name, calls, module_path, access):
        section, port, field_name = access
        matches = [result for path, result in calls if path == module_path]
        if len(matches) != 1:
            raise DefinitionError(
                f"{self.path}.{name}: descendant {module_path!r} was called "
                f"{len(matches)} times; expected exactly once"
            )
        values = matches[0].outputs if section == "output" else matches[0].outlets
        value = values[port]
        return getattr(value, field_name) if field_name is not None else value

    @staticmethod
    def _output_sum(calls, target):
        return sum(
            result.outputs[target]
            for _, result in calls
            if result.is_leaf and target in result.outputs
        )

    def _output_ratio(self, numerator, denominator):
        """Divide two earlier outputs; ``None`` when either is ``None`` or the divisor is zero."""
        top, bottom = getattr(self, numerator), getattr(self, denominator)
        if top is None or bottom is None:
            return None
        return ops.where(ops.eq(bottom, 0), None, ops.truediv(top, bottom))

    def _check_outputs(self, recorded):
        missing = sorted(self._outputs.keys() - recorded.keys())
        if missing:
            raise DefinitionError(f"{self.path}: outputs left unassigned: {missing}")

    def initial_state(self):
        """Return the initial states, nested by child name; ``None`` when nothing is stateful."""
        if self._states:
            return self._initial_states()
        states = {
            name: child_state
            for name, child in self.named_children()
            if (child_state := child.initial_state()) is not None
        }
        return states or None

    def step(self, state, dt, inlets):
        """Advance every declared state over ``dt`` seconds; return ``(next_state, result)``.

        ``state`` is the tree ``initial_state`` returns, or ``None`` for the initial states. The
        call runs as ``self(inlets)``; each stateful module called during it starts from its
        entry in ``state`` and records its end-of-step entry. A descendant that is stateful
        without declaring states steps itself, so a composite cannot step it and refuses.
        """
        if dt <= 0:
            raise ValidationError(
                f"{self.path}: dt = {dt} s; expected a positive step", code="invalid_design"
            )
        explicit = [
            path
            for path, module in self.named_modules()
            if path and module.stateful and not module._states
        ]
        if explicit:
            raise ValidationError(
                f"{self.path}: stateful descendants {', '.join(explicit)} need a step method "
                "on this composite that steps them",
                code="invalid_design",
            )
        start = state if state is not None else self.initial_state() or {}
        step = _Step(root=self, dt=dt, states=start, next_states=deepcopy(start))
        result = self._run((inlets,), {}, step)
        return step.next_states or None, result

    def start_states(self):
        """Return the state values a call of this module would start from now.

        Inside a running ``step`` these are the module's start-of-step entry, otherwise its
        initial states. A composite reads a stateful child's states before calling it when the
        child's outlet feeds back into the child's own inlet (the groundwater loop of an ATES
        plant).
        """
        parent = _current_call.get()
        return self._call_states(parent.step if parent is not None else None) or {}

    def trial_outlets(self, inlets):
        """Return the outlets of one call that no running call records, with outputs skipped.

        A composite that closes a circulation loop within one call evaluates trial passes with
        it, then calls each child once with the converged inlets, so formulas and balances see
        only that call. Controls and boundaries resolve as in a call without keywords, and
        pre-hooks run. A stateful module would evaluate at its initial states, so it is refused.
        """
        if self.stateful:
            raise ValidationError(
                f"{self.path}: stateful = True; expected a stateless module for a trial call",
                code="invalid_design",
            )
        token = _current_call.set(None)
        try:
            with no_outputs():
                return self(inlets).outlets
        finally:
            _current_call.reset(token)

    def _initial_states(self):
        """Return the validated initial value of every declared state."""
        return {name: state.default_value() for name, state in self._states.items()}

    def _call_states(self, step):
        """Return the state values one call starts from, or ``None`` without declared states."""
        if not self._states:
            return None
        if step is None:
            return self._initial_states()
        supplied = step.start(self._step_keys(step))
        unknown = sorted(supplied.keys() - self._states.keys())
        if unknown:
            raise ValidationError(
                f"{self.path}: unknown state {unknown[0]!r}; valid: {join_names(self._states)}"
                f"{did_you_mean(unknown[0], self._states)}",
                code="unknown_name",
            )
        return self._initial_states() | {
            name: self._states[name].validate(value) for name, value in supplied.items()
        }

    def _step_keys(self, step):
        """Return the child names that lead from the stepped module to this module."""
        if self is step.root:
            return ()
        prefix = step.root._path + "." if step.root._path else ""
        return tuple(self._path.removeprefix(prefix).split("."))

    def _next_states(self, inlets, outlets, dt):
        """Validate the end-of-step states that ``_advance_states`` returns."""
        values = self._advance_states(inlets, outlets, dt)
        if not isinstance(values, Mapping) or values.keys() != self._states.keys():
            raise ValidationError(
                f"{self.path}: _advance_states returned {sorted(values or ())}; expected "
                f"{join_names(self._states)}",
                code="invalid_design",
            )
        return {name: self._states[name].validate(value) for name, value in values.items()}

    def _advance_states(self, inlets, outlets, dt):
        """Return the end-of-step value of every declared state; stateful leaves override it."""
        raise NotImplementedError(f"{type(self).__name__} declares states without _advance_states")

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
            raise DefinitionError(
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
                "type": snake_case(module.name),
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
            raise ValidationError(
                f"{self.path}: state paths differ; missing={missing}, unexpected={unexpected}",
                code="invalid_format",
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

    def to_spec(self):
        """Return the plant file of this tree: format 2, a root ``type`` and flat ``params``."""
        return serialization.module_spec(self)

    def to_dict(self):
        """Return the plant file, the same document as ``to_spec``."""
        return self.to_spec()

    @classmethod
    def from_dict(cls, data):
        """Build this class and fill it from a format 2 plant file."""
        return serialization.module_from_spec(cls, data)

    def set_params(self, path, params, valid_from=None):
        """Store validated parameters of the module at ``path`` as a dated snapshot.

        The snapshot is the values in force at ``valid_from`` merged with ``params``; without a
        date the undated base entry and the current values change. Names may be dotted and
        values unit strings. Returns the module.

        Every route that sets parameters comes here. A composite that derives its children's
        values overrides this method (see ``modules.md``); a value for it, at any depth, reaches
        that override.
        """
        return design.set_params(self, path, params, valid_from)

    def params_at(self, path, time=None):
        """Return the parameter values of the module at ``path`` in force at ``time``."""
        return design.params_at(self, path, time)

    def param_history(self, path):
        """Return the dated parameter snapshots of the module at ``path``."""
        return design.param_history(self, path)

    def bindable(self, path):
        """Return what can be bound at ``path``, by section."""
        return design.bindable(self, path)

    def set_bindings(self, path, bindings):
        """Replace the bindings of the module at ``path``; units are checked. Returns the module."""
        return design.set_bindings(self, path, bindings)

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
            return f"{self._type_label}({extra})"
        rows = [f"{self._type_label}({extra}"]
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
            ("States", module._states),
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
