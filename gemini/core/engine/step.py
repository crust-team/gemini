"""Measured-boundary and chained module evaluation.

Both step functions return ``(outputs, skips, errors)``: outputs map module paths to
``(ModuleResult, Health)``, skips map paths to counted missing-data reasons and errors are
recorded module failures under ``on_error="record"``.
"""

import math
from collections import Counter
from copy import deepcopy

from gemini.core.physics import units
from gemini.core.types import Fluid, Health, Stream
from gemini.core.types.bindings import Binding, ModuleBindings
from gemini.core.types.declarations import UNSET
from gemini.errors import BindingError, MissingMeasurementError, StepError
from gemini.utils.strings import did_you_mean, join_names, join_path, split_path

VOLUMETRIC_UNITS = {"m3/h", "m3/s"}
"""Flow units converted to mass flow with the fluid density at the boundary."""


def _value(row, binding):
    value = row.get(binding.column)
    try:
        finite = value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        finite = False
    if not finite:
        raise MissingMeasurementError(binding.column)
    return units.to_si(value, binding.unit)


def _is_volumetric_mass_flow(module, name, binding):
    """Whether a kg/s control or boundary is bound to a volumetric flow column."""
    declaration = module.inputs().get(name)
    return (
        declaration is not None and declaration.unit == "kg/s" and binding.unit in VOLUMETRIC_UNITS
    )


def _input_values(module, bindings, row):
    """Return control and boundary values in SI; volumetric mass flows use the module state.

    The density comes from the module's ``pressure`` and ``temperature`` parameters, which
    ``BindingPlan`` requires for such a binding.
    """
    values = {
        name: _value(row, binding)
        for group in (bindings.controls, bindings.boundaries)
        for name, binding in group.items()
    }
    for name, binding in (bindings.controls | bindings.boundaries).items():
        if _is_volumetric_mass_flow(module, name, binding):
            values[name] *= module.fluid.properties(module.pressure, module.temperature).density
    return values


def _inlet_stream(module, fields, row, defaults):
    """Build one inlet stream from bound fields over its defaults and the module fluid."""
    values = dict(defaults)
    values.update({name: _value(row, binding) for name, binding in fields.items()})
    values.setdefault("fluid", module.fluid)
    values["fluid"] = Fluid.model_validate(values["fluid"])
    if "m_dot" in fields and fields["m_dot"].unit in VOLUMETRIC_UNITS:
        values["m_dot"] *= values["fluid"].properties(values["p"], values["T"]).density
    return Stream.model_validate(values)


def prepare(module, bindings, row, defaults=None):
    """Convert one measured boundary into keyword arguments and observations.

    For a heat exchanger with measured outlet temperatures, the observations also receive the
    inlet temperatures, mass flows and heat capacities that ``HeatExchanger.health`` reads.
    """
    kwargs = _input_values(module, bindings, row)
    for port, fields in bindings.inlets.items():
        kwargs[port] = _inlet_stream(module, fields, row, (defaults or {}).get(port, {}))
    measured = {name: _value(row, binding) for name, binding in bindings.measured.items()}
    if module.name == "heat_exchanger" and {"hot_out_T", "cold_out_T"} <= measured.keys():
        hot, cold = kwargs["hot_in"], kwargs["cold_in"]
        measured.update(
            hot_in_T=hot.T,
            cold_in_T=cold.T,
            m_dot_hot=hot.m_dot,
            m_dot_cold=cold.m_dot,
            cp_hot=hot.fluid.properties(hot.p, hot.T).cp_l,
            cp_cold=cold.fluid.properties(cold.p, cold.T).cp_l,
        )
    return kwargs, measured


def health_or_unavailable(module, result, measured):
    """Keep lack of diagnostics distinct from assessed nominal health."""
    health = module.health(result.outputs, measured) if result.outputs else None
    return health or Health(
        score=1,
        alarm=False,
        assessed=False,
        message="No diagnostic model or sufficient measurements",
    )


class BindingPlan:
    """Resolve module objects, bindings and required columns once for a run.

    ``entries`` holds ``(path, module, bindings, stream_defaults)`` per evaluated module. In
    simulate the only entry is the root with its inlet bindings; ``chained_inputs`` holds
    ``(path, module, bindings)`` for every leaf control or boundary that has a data column,
    and ``root_inlets`` the root inlet values given in ``plant.boundary["root_inputs"]``.
    """

    def __init__(self, plant, dataset, kind, only=None, on_error="record"):
        """Compile declarations and dataset bindings for repeated evaluations."""
        _check_only(plant, only)
        self.on_error = on_error
        self.stateful = any(module.stateful for module in plant.modules())
        self._dates = _parameter_dates(plant)
        self._started, self._next_change = False, None
        root_inputs = plant.boundary.get("root_inputs", {})
        self.root_inlets = {
            name: value for name, value in root_inputs.items() if name in plant.inlets()
        }
        self.chained_inputs, self.columns = [], set()
        bindings = plant.bindings
        if kind == "simulate":
            self.chained_inputs, self.columns = _simulation_inputs(plant, dataset)
            root = bindings.get("", ModuleBindings())
            bindings = {"": ModuleBindings(inlets=root.inlets)}
        self.entries = []
        for path, original in bindings.items():
            if kind != "simulate" and not _is_twin(plant, path, only):
                continue
            entry, columns = _compile_entry(plant, dataset, kind, path, original)
            self.entries.append(entry)
            self.columns |= columns
        missing = sorted(self.columns - set(dataset.names))
        if missing:
            raise BindingError(
                f"{plant.path}: bound columns = {join_names(missing)}; expected dataset columns"
                f"{did_you_mean(missing[0], dataset.names)}"
            )

    def apply_parameters(self, plant, at):
        """Apply dated design transitions once."""
        if not self._started or self._next_change is not None and at >= self._next_change:
            plant.apply_params_at(at)
            self._started = True
            self._next_change = next((date for date in self._dates if date > at), None)


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
    for input_path, declaration in plant.inputs(recurse=True).items():
        module_path, name = split_path(input_path)
        module = plant.get_submodule(module_path)
        binding = _input_binding(plant, dataset, input_path, module, declaration)
        if binding is None:
            if declaration.default is UNSET and name not in module._input_values:
                missing.append(input_path)
            continue
        bound = ModuleBindings()
        target = bound.controls if name in module.controls() else bound.boundaries
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
    group = original.controls if name in module.controls() else original.boundaries
    binding = group.get(name)
    if binding is None and input_path in dataset.names:
        binding = Binding(column=input_path, unit=declaration.unit or "-")
    if binding is None or binding.column not in dataset.names:
        return None
    binding = binding.model_copy(deep=True)
    binding.unit = dataset.unit(binding.column, binding.unit)
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
        binding.unit = dataset.unit(binding.column, binding.unit)
    return {binding.column for binding in group.values()}


def _drop_defaulted_fields(fields, defaults, dataset):
    """Remove inlet fields without a data column that have a default value."""
    for field, binding in list(fields.items()):
        if binding.column not in dataset.names and defaults.get(field) is not None:
            del fields[field]


def _check_volumetric_inputs(path, module, bound):
    """Require ``pressure``/``temperature`` parameters to convert a volumetric mass flow."""
    parameters = dict(module.named_parameters(recurse=False))
    for name, binding in (bound.controls | bound.boundaries).items():
        if _is_volumetric_mass_flow(module, name, binding) and not (
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


def twin_step(plant, sample, states, plan):
    """Evaluate each measured twin independently."""
    plan.apply_parameters(plant, sample.t)
    outputs, skips, errors = {}, {}, []
    for path, module, bound, defaults in plan.entries:
        try:
            outputs[path] = _evaluate_twin(path, module, bound, defaults, sample, states)
        except MissingMeasurementError as exc:
            skips.setdefault(path, Counter())[str(exc)] += 1
        except Exception as exc:
            if plan.on_error == "raise":
                raise StepError(f"{module.path}: {exc}") from exc
            errors.append(dict(module=path, message=str(exc), type=type(exc).__name__))
    return outputs, skips, errors


def _evaluate_twin(path, module, bound, defaults, sample, states):
    """Call one twin on its measured boundary; a stateful twin also advances its state."""
    kwargs, measured = prepare(module, bound, sample.row, defaults)
    applied = {name: kwargs.pop(name) for name in module.inputs() if name in kwargs}
    module.set_inputs(applied)
    if not module.stateful:
        prediction = module(kwargs)
        return prediction, health_or_unavailable(module, prediction, measured)
    state = _initial_state(path, module, bound, sample.row, states)
    next_state, prediction = module.step(state, sample.dt, kwargs)
    evaluated = prediction, health_or_unavailable(module, prediction, measured)
    states[path] = state if bound.state else next_state
    return evaluated


def _initial_state(path, module, bound, row, states):
    """Return the measured state, else the previous state, else the module's initial state.

    A twin skipped for missing data keeps its previous state; the skipped tick's dt is not
    integrated.
    """
    if bound.state:
        return {key: _value(row, binding) for key, binding in bound.state.items()}
    if path in states:
        return deepcopy(states[path])
    return module.initial_state()


def chained_step(plant, sample, states, plan):
    """Apply root bindings to one handwritten plant call; missing data skips the step."""
    plan.apply_parameters(plant, sample.t)
    _, _, bound, defaults = plan.entries[0]
    try:
        kwargs = plan.root_inlets | prepare(plant, bound, sample.row, defaults)[0]
        input_values = {}
        for path, module, input_bindings in plan.chained_inputs:
            values, _ = prepare(module, input_bindings, sample.row)
            input_values.update({join_path(path, name): value for name, value in values.items()})
    except MissingMeasurementError as exc:
        return {}, {"": Counter({str(exc): 1})}, []
    plant.set_inputs(input_values)
    if plan.stateful:
        states[""], result = plant.step(states.get("", plant.initial_state()), sample.dt, kwargs)
    else:
        result = plant(kwargs)
    outputs = {
        path: (child, health_or_unavailable(plant.get_submodule(path), child, {}))
        for path, child in result.leaves().items()
    }
    return outputs, {}, []
