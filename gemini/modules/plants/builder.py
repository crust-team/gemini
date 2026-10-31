"""Plants built from data: a ``Module`` whose forward runs its children in connection order."""

from gemini.errors import ValidationError
from gemini.errors.base import reported
from gemini.modules._utils.container import ModuleList
from gemini.modules.module import Module
from gemini.modules.plants import listing, outputs, reader, writer
from gemini.modules.plants.factory import make_module
from gemini.modules.plants.plan import (
    STATE,
    Link,
    compile_plan,
    is_group,
    loop_through,
)
from gemini.modules.plants.ports import PortResolver
from gemini.types.declarations import Inlet, Outlet
from gemini.utils.strings import join_path, snake_case


class Plant(PortResolver, Module):
    """A plant built from named modules and connections, a normal composite ``Module``.

    ``add`` registers a module, ``connect`` wires an outlet to an inlet and ``to_spec`` writes the
    plant file. Every port of a child is connected or named as a plant port; a plant port exists
    only when named. ``name`` is the name given.
    """

    def __init__(self, name="plant"):
        """Start an empty plant called ``name``."""
        object.__setattr__(self, "_name", name)
        super().__init__()
        self._connections = []
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

    def _refresh(self):
        self._plan = None
        for declarations in (self._inlets, self._outlets, self._outputs):
            declarations.clear()
        for side, declare in (("inlets", Inlet), ("outlets", Outlet)):
            for name, (path, port) in self._port_map(side).items():
                end = getattr(self.get_module(path), side)()[port]
                self._register_declaration(name, declare(end.type, kind=end.kind))
        if self._output_specs is None:
            outputs.declare_automatic(self)
            return
        for name, spec in self._output_specs.items():
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
        """Return the plant file: format 2, modules, connections and the sections of the tree."""
        return writer.plant_spec(self)

    @classmethod
    def from_dict(cls, data):
        """Build a plant of this class from a format 2 plant file."""
        return reader.read(cls, data)

    def validate(self, on_error="raise"):
        """Check the plant's spec as ``gm.plants.validate`` does; the same ``on_error``."""
        return reported(reader.problems(type(self), self.to_spec()), on_error)

    def _compiled(self):
        if self._plan is None:
            self._plan = compile_plan(self)
        return self._plan

    def _argument(self, source, inlets, results):
        if source[0] == "inlet":
            return inlets[source[1]]
        return results[source[1]].outlets[source[2]]

    def _plan_outlets(self, results):
        for name, (path, port) in self._compiled().outlets.items():
            yield name, results[path].outlets[port]

    def forward(self, inlets):
        """Call the modules in connection order and return the plant outlets."""

        # Modules
        results = {}
        for step in self._compiled().steps:
            arguments = {
                port: self._argument(source, inlets, results)
                for port, source in step.arguments.items()
            }
            results[step.path] = step.module(**arguments)

        # Outlets
        outlets = dict(self._plan_outlets(results))
        return outlets
