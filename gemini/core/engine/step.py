"""Measured-boundary and chained module evaluation."""

import math
from collections import Counter
from copy import deepcopy

from gemini.core.physics import units
from gemini.core.types import Fluid, Health, Stream
from gemini.core.types.declarations import UNSET


class MissingMeasurement(ValueError):
    """A required bound column is absent or nonfinite."""


def _value(row, binding):
    value = row.get(binding.column)
    try:
        finite = value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        finite = False
    if not finite:
        raise MissingMeasurement(binding.column)
    return units.to_si(value, binding.unit)


def prepare(module, bindings, row, defaults=None):
    """Convert one measured boundary into keyword arguments and observations."""
    kwargs = {
        name: _value(row, binding)
        for group in (bindings.controls, bindings.boundaries)
        for name, binding in group.items()
    }
    for name, binding in (bindings.controls | bindings.boundaries).items():
        declaration = module.inputs().get(name)
        if (
            declaration is not None
            and declaration.unit == "kg/s"
            and binding.unit
            in {
                "m3/h",
                "m3/s",
            }
        ):
            pressure = getattr(module, "pressure", 1e5)
            temperature = getattr(module, "temperature", 300)
            kwargs[name] *= module.fluid.properties(pressure, temperature).density
    for port, fields in bindings.inlets.items():
        values = dict((defaults or {}).get(port, {}))
        values.update({name: _value(row, binding) for name, binding in fields.items()})
        values.setdefault("fluid", module.fluid)
        values["fluid"] = Fluid.model_validate(values["fluid"])
        if "m_dot" in fields and fields["m_dot"].unit in {"m3/h", "m3/s"}:
            if not {"p", "T"} <= values.keys():
                raise MissingMeasurement(f"{port}: pressure and temperature required")
            values["m_dot"] *= values["fluid"].properties(values["p"], values["T"]).density
        kwargs[port] = Stream.model_validate(values)
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
    """Resolve module objects and required columns once for a run."""

    def __init__(self, plant, dataset, kind, only=None, on_error="record"):
        """Compile declarations and dataset bindings for repeated evaluations."""
        from gemini.core.types.bindings import Binding, ModuleBindings

        self.entries, self.columns, self.chained_inputs = [], set(), []
        self._started, self._next_change = False, None
        self._dates = sorted(
            {
                snapshot.valid_from
                for module in plant.modules()
                for snapshot in module.param_history
                if snapshot.valid_from is not None
            }
        )
        self.stateful = any(module.stateful for module in plant.modules())
        self.on_error = on_error
        self.skips, self.errors = {}, []
        if only is not None:
            for path in only:
                plant.get_submodule(path)
                if path not in plant.bindings:
                    raise ValueError(f"{path}: no measured boundary bindings")
        bindings = plant.bindings
        if kind == "simulate":
            root = bindings.get("", ModuleBindings()).model_copy(deep=True)
            root.controls, root.boundaries = {}, {}
            root.measured, root.state = {}, {}
            bindings = {"": root}
            missing_inputs = []
            for input_path, declaration in plant.inputs(recurse=True).items():
                module_path, _, name = input_path.rpartition(".")
                module = plant.get_submodule(module_path)
                original = plant.bindings.get(module_path, ModuleBindings())
                group = original.controls if name in module.controls() else original.boundaries
                binding = group.get(name)
                if binding is None and input_path in dataset.names:
                    binding = Binding(column=input_path, unit=declaration.unit or "-")
                if binding is not None and binding.column in dataset.names:
                    binding = binding.model_copy(deep=True)
                    if binding.column in dataset.columns:
                        binding.unit = dataset.columns[binding.column].unit
                    bound = ModuleBindings()
                    target = bound.controls if name in module.controls() else bound.boundaries
                    target[name] = binding
                    self.chained_inputs.append((module_path, module, bound))
                    self.columns.add(binding.column)
                elif declaration.default is UNSET and name not in module._input_values:
                    missing_inputs.append(input_path)
            if missing_inputs:
                raise ValueError(
                    "Simulation inputs have no data column or default: "
                    + ", ".join(sorted(missing_inputs))
                )
        for path, original in bindings.items():
            if kind != "simulate" and (not path or only is not None and path not in only):
                if path or plant._children or only is not None and path not in only:
                    continue
            bound = original.model_copy(deep=True)
            module = plant.get_submodule(path)
            groups = [
                bound.controls,
                bound.boundaries,
                bound.measured,
                bound.state,
                *bound.inlets.values(),
            ]
            for group in groups:
                for field, binding in list(group.items()):
                    if kind == "simulate" and binding.column not in dataset.names:
                        if _default_for(plant, path, group, field, bound) is not None:
                            del group[field]
                            continue
                    if binding.column in dataset.columns:
                        binding.unit = dataset.columns[binding.column].unit
                    self.columns.add(binding.column)
            defaults = deepcopy(plant.boundary.get("stream_defaults", {}).get(path, {}))
            if path == "":
                root = plant.boundary.get("root_inputs", {})
                for inlet in bound.inlets:
                    if inlet in root:
                        defaults.setdefault(inlet, root[inlet])
            self.entries.append((path, module, bound, defaults))
        missing = sorted(self.columns - set(dataset.names))
        if missing:
            raise ValueError("Dataset is missing bound columns: " + ", ".join(missing))

    def apply_parameters(self, plant, at):
        """Apply dated design transitions once."""
        if not self._started or self._next_change is not None and at >= self._next_change:
            plant.apply_params_at(at)
            self._started = True
            self._next_change = next((date for date in self._dates if date > at), None)


def _default_for(plant, path, group, field, bound):
    defaults = plant.boundary.get("root_inputs", {}) if path == "" else {}
    if group is bound.controls or group is bound.boundaries:
        return defaults.get(field)
    for port, fields in bound.inlets.items():
        if group is fields:
            return defaults.get(port, {}).get(field)
    return None


def twin_step(plant, sample, states, plan):
    """Evaluate each measured twin independently."""
    plan.apply_parameters(plant, sample.t)
    results = {}
    plan.skips, plan.errors = {}, []
    for path, module, bound, defaults in plan.entries:
        try:
            kwargs, measured = prepare(module, bound, sample.row, defaults)
            applied = {name: kwargs.pop(name) for name in module.inputs() if name in kwargs}
            module.set_inputs(applied)
            if module.stateful:
                state = (
                    {key: _value(sample.row, binding) for key, binding in bound.state.items()}
                    if bound.state
                    else deepcopy(states[path]) if path in states else module.initial_state()
                )
                next_state, prediction = module.step(state, sample.dt, **kwargs)
            else:
                prediction = module(**kwargs)
            results[path] = prediction, health_or_unavailable(module, prediction, measured)
            if module.stateful:
                states[path] = state if bound.state else next_state
        except MissingMeasurement as exc:
            plan.skips.setdefault(path, Counter())[str(exc)] += 1
        except Exception as exc:
            if plan.on_error == "raise":
                raise ValueError(f"{module.path}: {exc}") from exc
            plan.errors.append(dict(module=path, message=str(exc), type=type(exc).__name__))
    return results


def chained_step(plant, sample, states, plan):
    """Apply root bindings to one handwritten plant call."""
    plan.apply_parameters(plant, sample.t)
    plan.skips, plan.errors = {}, []
    _, _, bound, defaults = plan.entries[0]
    kwargs = {
        name: value
        for name, value in deepcopy(plant.boundary.get("root_inputs", {})).items()
        if name in plant.inlets()
    }
    measured_kwargs, _ = prepare(plant, bound, sample.row, defaults)
    kwargs.update(measured_kwargs)
    input_values = {}
    for path, module, input_bindings in plan.chained_inputs:
        values, _ = prepare(module, input_bindings, sample.row)
        input_values.update(
            {f"{path}.{name}" if path else name: value for name, value in values.items()}
        )
    plant.set_inputs(input_values)
    if plan.stateful:
        states[""], result = plant.step(states.get("", plant.initial_state()), sample.dt, **kwargs)
    else:
        result = plant(**kwargs)
    return {
        path: (child, health_or_unavailable(plant.get_submodule(path), child, {}))
        for path, child in result.leaves().items()
    }
