"""The binding plan of a run: which columns feed which module inputs, and in which order.

``BindingPlan`` resolves the modules, bindings and columns of a run once, with the dataset's
units. Each evaluated module becomes a ``Twin``: its ``sources`` list the columns it reads in the
order a missing value is reported, and the runner (``gemini.core.engine.runner``) evaluates it
over chunks of ticks.
"""

from copy import deepcopy
from dataclasses import dataclass, field

from gemini.core.data.dataset import bound_unit
from gemini.core.types.bindings import Binding, ModuleBindings
from gemini.core.types.declarations import UNSET
from gemini.errors import BindingError
from gemini.utils.strings import did_you_mean, join_names, join_path, split_path

VOLUMETRIC_UNITS = {"m3/h", "m3/s"}
"""Flow units converted to mass flow with the fluid density at the boundary."""


def is_volumetric_mass_flow(module, name, binding):
    """Whether a kg/s control or boundary is bound to a volumetric flow column."""
    declaration = module.inputs(recurse=False).get(name)
    return (
        declaration is not None and declaration.unit == "kg/s" and binding.unit in VOLUMETRIC_UNITS
    )


@dataclass(frozen=True)
class Source:
    """One thing a twin reads from the data, in the order a missing value is reported.

    ``kind`` is ``"input"`` (a control or boundary named ``key``), ``"field"`` (``key`` is the
    ``(port, field)`` of an inlet stream), ``"stream"`` (the inlet ``key`` is complete: its
    limits are checked here), ``"measured"`` (an observation named ``key``) or ``"state"`` (a
    measured state named ``key``). ``quantity`` is the declared quantity of a difference
    quantity and ``density`` the module whose reference state converts a volumetric mass flow.
    """

    kind: str
    key: object
    binding: Binding | None = None
    quantity: str | None = None
    density: object = None


@dataclass
class Twin:
    """A module evaluated against data: the module, its sources and its inlet defaults."""

    path: str
    module: object
    sources: list
    defaults: dict
    stepped: bool = False
    constants: dict = field(default_factory=dict)
    leaves: bool = False

    def inputs(self):
        """Return the sources of the controls and boundaries."""
        return [source for source in self.sources if source.kind == "input"]

    def kinds(self, kind):
        """Return the sources of one kind."""
        return [source for source in self.sources if source.kind == kind]

    @property
    def ports(self):
        """The bound inlet ports, in binding order."""
        return [source.key for source in self.sources if source.kind == "stream"]


def _input_source(module, name, binding, feed=None):
    declaration = module.inputs(recurse=False).get(name)
    quantity = declaration.quantity if declaration is not None else None
    density = module if is_volumetric_mass_flow(module, name, binding) else None
    return Source("input", feed or name, binding, quantity, density)


def _replay_sources(module, bound):
    """Return the sources of a measured twin: inputs, inlets, observations and states."""
    sources = [
        _input_source(module, name, binding)
        for group in (bound.controls, bound.boundaries)
        for name, binding in group.items()
    ]
    sources += _inlet_sources(bound.inlets)
    outputs = module.outputs(recurse=False)
    for name, binding in bound.measured.items():
        declaration = outputs.get(name)
        quantity = declaration.quantity if declaration is not None else None
        sources.append(Source("measured", name, binding, quantity))
    sources += [Source("state", key, binding) for key, binding in bound.state.items()]
    return sources


def _inlet_sources(inlets):
    """Return, per inlet, the sources of its fields and the check of the finished stream."""
    sources = []
    for port, fields in inlets.items():
        sources += [Source("field", (port, name), binding) for name, binding in fields.items()]
        sources.append(Source("stream", port))
    return sources


class BindingPlan:
    """Resolve module objects, bindings and required columns once for a run.

    ``twins`` holds one ``Twin`` per evaluated module. In simulate the only twin is the plant,
    reading its root inlets and every leaf control or boundary that has a data column;
    ``root_inlets`` holds the root inlet values given in ``plant.boundary["root_inputs"]``.
    ``one_tick`` tells that the run cannot evaluate more than one tick at a time: a stateful
    module is stepped, or a twin sits below another twin and reads what that twin persisted.
    """

    def __init__(self, plant, dataset, kind, only=None, on_error="record"):
        """Compile declarations and dataset bindings for repeated evaluations."""
        _check_only(plant, only)
        self.kind = kind
        self.on_error = on_error
        self._dates = _parameter_dates(plant)
        root_inputs = plant.boundary.get("root_inputs", {})
        self.root_inlets = {
            name: value for name, value in root_inputs.items() if name in plant.inlets()
        }
        self.twins, self.columns = [], set()
        if kind == "simulate":
            self._simulation(plant, dataset)
        else:
            self._measured(plant, dataset, only)
        missing = sorted(self.columns - set(dataset.names))
        if missing:
            raise BindingError(
                f"{plant.path}: bound columns = {join_names(missing)}; expected dataset columns"
                f"{did_you_mean(missing[0], dataset.names)}"
            )
        paths = [twin.path for twin in self.twins]
        nested = any(_is_below(path, paths) for path in paths)
        self.one_tick = nested or any(twin.stepped for twin in self.twins)

    def _simulation(self, plant, dataset):
        """Add the plant as the one twin, with its leaf inputs read from the data."""
        chained, columns = _simulation_inputs(plant, dataset)
        root = plant.bindings.get("", ModuleBindings())
        entry, entry_columns = _compile_entry(
            plant, dataset, "simulate", "", ModuleBindings(inlets=root.inlets)
        )
        _, _, bound, defaults = entry
        sources = _inlet_sources(bound.inlets)
        for module_path, module, input_bindings in chained:
            ((name, binding),) = (input_bindings.controls | input_bindings.boundaries).items()
            sources.append(_input_source(module, name, binding, join_path(module_path, name)))
        stepped = any(module.stateful for module in plant.modules())
        constants = {
            port: value for port, value in self.root_inlets.items() if port not in bound.inlets
        }
        self.twins.append(Twin("", plant, sources, defaults, stepped, constants, leaves=True))
        self.columns |= columns | entry_columns

    def _measured(self, plant, dataset, only):
        """Add one twin per bound module that replay evaluates."""
        for path, original in plant.bindings.items():
            if not _is_twin(plant, path, only):
                continue
            (_, module, bound, defaults), columns = _compile_entry(
                plant, dataset, "replay", path, original
            )
            sources = _replay_sources(module, bound)
            self.twins.append(Twin(path, module, sources, defaults, module.stateful))
            self.columns |= columns

    def parameter_stretches(self, times):
        """Return the ``(start, stop)`` index ranges of ticks that share one parameter snapshot.

        The snapshot is applied at the first tick and again at the first tick at or after each
        later date. No ticks give no stretch.
        """
        if not len(times):
            return []
        starts, change = [0], self._change_after(times[0])
        for index, at in enumerate(times):
            if change is not None and at >= change:
                starts.append(index)
                change = self._change_after(at)
        return list(zip(starts, [*starts[1:], len(times)]))

    def _change_after(self, at):
        return next((date for date in self._dates if date > at), None)


def _is_below(path, paths):
    """Whether another twin sits below the twin at ``path``."""
    return bool(path) and any(other.startswith(path + ".") for other in paths)


def _check_only(plant, only):
    """Reject ``only`` paths that are not modules with measured bindings."""
    for path in only or ():
        plant.get_submodule(path)
        if path not in plant.bindings:
            raise BindingError(
                f"{plant.path}: only path = {path!r}; expected a module with measured "
                f"bindings{did_you_mean(path, plant.bindings)}"
            )


def _parameter_dates(plant):
    """Return the sorted instants at which any dated parameter snapshot starts."""
    return sorted(
        {
            snapshot.valid_from
            for module in plant.modules()
            for snapshot in module.param_history
            if snapshot.valid_from is not None
        }
    )


def _is_twin(plant, path, only):
    """Whether replay evaluates the bindings at ``path`` as a measured twin.

    The root entry of a composite plant describes the plant's own boundary, which replay never
    evaluates; ``only`` selects a subset of twins.
    """
    is_selected = only is None or path in only
    return is_selected and not (path == "" and not plant.is_leaf)


def _simulation_inputs(plant, dataset):
    """Return the leaf inputs with a data column and their columns; reject inputs with none."""
    chained, columns, missing = [], set(), []
    for input_path, declaration in plant.inputs().items():
        module_path, name = split_path(input_path)
        module = plant.get_submodule(module_path)
        binding = _input_binding(plant, dataset, input_path, module, declaration)
        if binding is None:
            if declaration.default is UNSET and not module.has_input_value(name):
                missing.append(input_path)
            continue
        bound = ModuleBindings()
        target = bound.controls if name in module.controls(recurse=False) else bound.boundaries
        target[name] = binding
        _check_volumetric_inputs(module_path, module, bound)
        chained.append((module_path, module, bound))
        columns.add(binding.column)
    if missing:
        raise BindingError(
            f"{plant.path}: simulation inputs = {join_names(sorted(missing))}; expected a data "
            "column or a default for each"
        )
    return chained, columns


def _input_binding(plant, dataset, input_path, module, declaration):
    """Return a leaf input's binding when its column exists, with the dataset's unit.

    An input without a binding is bound to a column named after its dotted path.
    """
    module_path, name = split_path(input_path)
    original = plant.bindings.get(module_path, ModuleBindings())
    group = original.controls if name in module.controls(recurse=False) else original.boundaries
    binding = group.get(name)
    if binding is None and input_path in dataset.names:
        binding = Binding(column=input_path, unit=declaration.unit or "-")
    if binding is None or binding.column not in dataset.names:
        return None
    binding = binding.model_copy(deep=True)
    binding.unit = bound_unit(dataset, binding)
    return binding


def _compile_entry(plant, dataset, kind, path, original):
    """Return one plan entry and its columns, with units taken from the dataset.

    In simulate, an inlet field whose column is absent is dropped when
    ``plant.boundary["root_inputs"]`` gives it a default.
    """
    bound = original.model_copy(deep=True)
    module = plant.get_submodule(path)
    root_inputs = plant.boundary.get("root_inputs", {})
    columns = set()
    for group in (bound.controls, bound.boundaries, bound.measured, bound.state):
        columns |= _resolve_units(group, dataset)
    for port, fields in bound.inlets.items():
        if kind == "simulate":
            _drop_defaulted_fields(fields, root_inputs.get(port, {}), dataset)
        columns |= _resolve_units(fields, dataset)
    defaults = deepcopy(plant.boundary.get("stream_defaults", {}).get(path, {}))
    if path == "":
        for inlet in bound.inlets:
            if inlet in root_inputs:
                defaults.setdefault(inlet, root_inputs[inlet])
    _check_volumetric_inputs(path, module, bound)
    _check_volumetric_inlets(path, bound, defaults)
    return (path, module, bound, defaults), columns


def _resolve_units(group, dataset):
    """Take each binding's unit from the dataset metadata; return the bound columns."""
    for binding in group.values():
        binding.unit = bound_unit(dataset, binding)
    return {binding.column for binding in group.values()}


def _drop_defaulted_fields(fields, defaults, dataset):
    """Remove inlet fields without a data column that have a default value."""
    for name, binding in list(fields.items()):
        if binding.column not in dataset.names and defaults.get(name) is not None:
            del fields[name]


def _check_volumetric_inputs(path, module, bound):
    """Require ``pressure``/``temperature`` parameters to convert a volumetric mass flow."""
    parameters = dict(module.named_parameters(recurse=False))
    for name, binding in (bound.controls | bound.boundaries).items():
        if is_volumetric_mass_flow(module, name, binding) and not (
            {"pressure", "temperature"} <= parameters.keys()
        ):
            raise BindingError(
                f"{path or module.path}: {name} = {binding.column!r} [{binding.unit}]; expected "
                "a module with pressure and temperature parameters to convert it to kg/s"
            )


def _check_volumetric_inlets(path, bound, defaults):
    """Require ``p`` and ``T`` (bound or default) for an inlet whose flow is volumetric."""
    for port, fields in bound.inlets.items():
        flow = fields.get("m_dot")
        known = fields.keys() | defaults.get(port, {}).keys()
        if flow is not None and flow.unit in VOLUMETRIC_UNITS and not {"p", "T"} <= known:
            raise BindingError(
                f"{path}: {port}.m_dot = {flow.column!r} [{flow.unit}]; expected p and T "
                "bindings or defaults to convert it to kg/s"
            )
