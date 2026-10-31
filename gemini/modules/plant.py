"""Plants: a ``Module`` that connects its children and whose forward runs them in that order."""

from gemini.errors import ValidationError
from gemini.errors.base import reported
from gemini.modules._utils import design
from gemini.modules._utils.serialization import module_spec, tree_params
from gemini.modules.container import ModuleList
from gemini.modules.module import Module
from gemini.modules.plants._utils import listing, outputs, reader, writer
from gemini.modules.plants._utils.factory import make_module
from gemini.modules.plants._utils.plan import (
    STATE,
    Link,
    compile_plan,
    is_group,
    loop_through,
    port_ends,
)
from gemini.modules.plants._utils.ports import PortResolver
from gemini.physics import energy
from gemini.types.declarations import Inlet, Outlet
from gemini.utils.strings import join_path, snake_case


class Plant(PortResolver, Module):
    """Named modules and the connections between them: every composite is a ``Plant``.

    A plant class declares its children, ports and connections in ``__init__``, in the sections
    ``# Modules``, ``# Parameters``, ``# Inlets``, ``# Outlets``, ``# Connections``, ``# Outputs``,
    and never writes ``forward``; ``gm.Plant(name)`` builds one with ``add`` and ``connect``. A
    child assigned as an attribute is registered as ``add`` does. Every port of a child is
    connected or named as a plant port; a plant port exists only when named. ``name`` is the name
    given, by default the name of the class.

    A plant may override ``set_params`` to derive its children's values from design values. What
    such a call states explicitly is remembered and wins over what is derived, derived values are
    never stored, and the fluid of a plant passes to its children.
    """

    def __init__(self, name=None):
        """Start an empty plant called ``name``."""
        if name is None:
            name = "plant" if type(self) is Plant else type(self).__name__
        object.__setattr__(self, "_name", name)
        super().__init__()
        self._size = {}
        self._connections = []
        self._declared = set()
        self._derived_params = set()
        self._stated_child_params = set()
        self._listed = {"inlets": {}, "outlets": {}}
        self._output_specs = None
        self._stated = {}
        self._baselines = {}
        self._sections = {}
        self._plan = None

    @classmethod
    def _empty(cls, name):
        plant = cls.__new__(cls)
        Plant.__init__(plant, name)
        return plant

    @property
    def name(self):
        """Return the name given to the plant."""
        return self._name

    @property
    def path(self):
        """Return the assigned tree path, or the snake case name of a standalone plant."""
        return self._path or snake_case(self._name)

    @property
    def _type_label(self):
        return self._name

    @property
    def fluid(self):
        """Return the fluid of the plant."""
        return self._fluid

    @fluid.setter
    def fluid(self, value):
        """Set the fluid of the plant and of every module below it, and derive again."""
        for module in self.modules():
            module._set_own_fluid(value)

    def _set_own_fluid(self, value):
        """Set the fluid of this plant alone and derive again."""
        super()._set_own_fluid(value)
        if self._derives_params():
            self.set_params("", {})

    def _derives_params(self):
        """Return whether this class overrides ``set_params`` to derive its children's values."""
        return type(self).set_params is not Plant.set_params

    def set_params(self, path, params, valid_from=None):
        """Store parameters as ``Module.set_params`` does and remember what the root was given."""
        if not path:
            kept = {key: value for key, value in params.items() if key not in self._derived_params}
            self._stated[""] = self._stated.get("", {}) | kept
        return super().set_params(path, params, valid_from)

    def _own_values(self, params, valid_from=None):
        """Return the own parameters in force at ``valid_from`` with those of ``params``, in SI."""
        given = {name: value for name, value in params.items() if name in self._parameters}
        checked = {name: self._parameters[name].validate(value) for name, value in given.items()}
        return self._params_at(valid_from) | checked

    def _keep_derived(self, derived, params):
        """Return the ``derived`` child values that no explicit value replaces, and record them.

        A deriving ``set_params`` calls this with its derived values and the ``params`` of the
        call. A dotted name in ``params`` is an explicit child value, now and in later calls, and
        so is a child value assigned on the child. The names kept are the ones ``to_dict`` leaves
        out.
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

    def add_module(self, name, module):
        """Register a child assigned as an attribute, as ``add`` does."""
        super().add_module(name, module)
        self._note_child(name, module)

    def _note_child(self, key, module):
        """Record that nothing has been stated yet for ``module`` and what it starts from."""
        if key in self._baselines:
            return
        self._baselines[key] = {}
        if is_group(module):
            for name, child in module.named_children():
                self._note_child(join_path(key, name), child)
            return
        self._stated[key] = {}
        self._baselines[key] = writer.baseline_of(module)

    def add(self, type, name=None, params=None):
        """Add a module of registry name or class ``type`` and return it.

        ``params`` is one dict of design values, the dict ``set_params`` takes: unit strings
        accepted, dotted names for a composite. ``name`` defaults to the snake case type, numbered
        when taken; a dotted name adds into a group such as ``filters.hot``.
        """
        module, type_name = make_module(type)
        key = self._free_name(name, type_name)
        baseline = writer.baseline_of(module)
        stated = dict(params or {})
        module.set_params("", stated)
        self._attach(key, module, stated, baseline)
        return module

    def _attach(self, key, module, stated, baseline):
        """Register ``module`` under the (possibly dotted) ``key`` with the params as stated."""
        parent_path, _, local = key.rpartition(".")
        parent = self.get_module(parent_path)
        if parent is not self and not is_group(parent):
            raise ValidationError(f"{key}: {parent_path!r} is not a group", path="name")
        if isinstance(parent, ModuleList):
            parent.append(module)
        else:
            parent.add_module(local, module)
        self._stated[key] = stated
        self._baselines[key] = baseline
        self._refresh()

    def _free_name(self, name, type_name):
        taken = {path for path, _ in self.named_modules()}
        if name is not None:
            if name in taken:
                raise ValidationError(f"add: name {name!r} is already taken", path="name")
            return name
        base = snake_case(type_name)
        candidates = [base] + [f"{base}_{number}" for number in range(2, len(taken) + 3)]
        return next(item for item in candidates if item not in taken)

    def connect(self, source, target, type=None):
        """Connect an outlet to an inlet; ``type="state"`` closes a loop through the last step.

        An end is a module, a port declaration or ``"path.port"``. A bare module path picks its
        only free port of a fitting kind; several fitting pairs raise ``ambiguous_port``.
        A bare word that names no module is a plant port: ``connect("return_in",
        "heat_exchanger.cold_in")`` names a plant inlet.
        """
        self._link(source, target, type, explicit=False)

    def _link(self, source, target, type, explicit):
        """Add one connection or name one plant port; ``explicit`` requires ``path.port`` ends."""
        if type not in (None, STATE):
            raise ValidationError(
                f"type = {type!r}; expected 'state' or null", path="type", code="invalid_value"
            )
        if self._is_port_name(source):
            return self._name_port("inlets", source, target, explicit)
        if self._is_port_name(target):
            return self._name_port("outlets", target, source, explicit)
        first = self._candidates(source, "source", explicit)
        second = self._candidates(target, "target", explicit)
        (path, port, _), (target_path, target_port, _) = self._choose(first, second)
        self._add_connection(path, port, target_path, target_port, type)

    def _add_connection(self, path, port, target_path, target_port, connection_type):
        item = {"source": join_path(path, port), "target": join_path(target_path, target_port)}
        if connection_type == STATE:
            item["type"] = STATE
        self._connections.append(item)
        link = Link("", (path, port), (target_path, target_port), connection_type)
        loop = loop_through(self, link)
        if loop is not None:
            self._connections.pop()
            raise ValidationError(
                f"loop without state: {' -> '.join(loop)}; close it with type='state'",
                path="target",
                code="loop_without_state",
            )
        self._refresh()

    def _register_declaration(self, name, declaration):
        """Register a declaration; a port assigned by a plant class stays through ``_refresh``."""
        if isinstance(declaration, (Inlet, Outlet)):
            self._declared.add(name)
        super()._register_declaration(name, declaration)

    def _refresh(self):
        self._plan = None
        self._outputs.clear()
        for side, declare in (("inlets", Inlet), ("outlets", Outlet)):
            for name, ends in self._port_map(side).items():
                if name in self._declared:
                    continue
                path, port = port_ends(ends)[0]
                end = getattr(self.get_module(path), side)()[port]
                registry = getattr(self, f"_{side}")
                registry.pop(name, None)
                Module._register_declaration(self, name, declare(end.type, kind=end.kind))
        for name, spec in (self._output_specs or {}).items():
            outputs.declare_output(self, name, spec)

    def _connection_list(self):
        """Return the plant's connections as ``[{source, target, kind, type}]``.

        ``kind`` is the label of the labelled end, ``None`` when both ends take anything.
        """
        return listing.connection_list(self)

    def summary(self):
        """Return a text table of the modules: type, category, inbound connections, parameters."""
        return listing.summary(self)

    def to_spec(self):
        """Return the plant file: format 2, modules, connections and the sections of the tree.

        A plant class with design values of its own writes them as flat values instead.
        """
        if type(self) is Plant:
            return writer.plant_spec(self)
        self._baselines[""] = tree_params(type(self)(**self._size))
        params = writer.params_spec(self, "", self)
        if not set(params) & set(self._parameters):
            return writer.plant_spec(self)
        return module_spec(self) | {"params": params}

    @classmethod
    def from_dict(cls, data):
        """Build a plant of this class from a format 2 plant file."""
        return reader.read(cls, data)

    def validate(self, on_error="raise"):
        """Check the plant's spec as ``gm.plants.validate`` does; the same ``on_error``."""
        spec = self.to_spec()
        return reported(reader.problems(type(self), spec) + reader.root_problems(spec), on_error)

    def _compiled(self):
        if self._plan is None:
            self._plan = compile_plan(self)
        return self._plan

    def _argument(self, source, inlets, results, offers):
        if source[0] == "many":
            return [self._argument(item, inlets, results, offers) for item in source[1]]
        if source[0] == "inlet":
            return inlets[source[1]]
        if source[0] == "offer":
            return offers[source[1]][source[2]]
        if source[0] == "drawn":
            return results[source[1]].inlets[source[2]]
        return results[source[1]].outlets[source[2]]

    def _plant_value(self, values):
        """Return the value of a plant port: its one end, or the sum of what its ends carry."""
        return values[0] if len(values) == 1 else energy.total_power(values)

    def _plan_outlets(self, results):
        plan = self._compiled()
        for name, ends in plan.outlets.items():
            yield name, self._plant_value([results[path].outlets[port] for path, port in ends])
        for name, ends in plan.given.items():
            yield name, self._plant_value([results[path].inlets[port] for path, port in ends])

    def forward(self, inlets):
        """Call the modules in connection order and return the plant outlets."""

        # Modules
        results, offers = {}, {}
        for step in self._compiled().steps:
            arguments = {
                port: self._argument(source, inlets, results, offers)
                for port, source in step.arguments.items()
            }
            if step.offer:
                offers[step.path] = step.module.offer(arguments)
            else:
                results[step.path] = step.module(**arguments)

        # Outlets
        outlets = dict(self._plan_outlets(results))
        return outlets
