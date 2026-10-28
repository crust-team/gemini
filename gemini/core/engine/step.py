"""Independent equipment evaluation on measured boundaries, with explicit missing-data skips."""

import math
from collections import Counter
from copy import deepcopy

from gemini.core.physics import units
from gemini.core.types.flows import Stream
from gemini.core.types.results import Health


class MissingMeasurement(ValueError):
    """A required bound column is absent or nonfinite in this observation."""


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
    """Convert a measured boundary to validated SI controls, streams and output measurements."""
    inputs = {name: _value(row, binding) for name, binding in bindings.inputs.items()}
    for name, binding in bindings.inputs.items():
        if name == "m_dot" and binding.unit in ("m3/h", "m3/s"):
            p, T = getattr(module.params, "pressure", 1e5), getattr(
                module.params, "temperature", 300
            )
            inputs[name] *= module.fluid.properties(p, T).density
    streams = {}
    for port, fields in bindings.streams.items():
        values = dict((defaults or {}).get(port, {}))
        values.update({name: _value(row, binding) for name, binding in fields.items()})
        values.setdefault("fluid", module.fluid)
        if "m_dot" in fields and fields["m_dot"].unit in ("m3/h", "m3/s"):
            if not {"p", "T"} <= values.keys():
                raise MissingMeasurement(
                    f"{port}: pressure and temperature required for volume flow"
                )
            values["m_dot"] *= values["fluid"].properties(values["p"], values["T"]).density
        streams[port] = Stream.model_validate(values)
    measured = {name: _value(row, binding) for name, binding in bindings.measured.items()}
    if module.name == "heatexchanger" and {"hot_out_T", "cold_out_T"} <= measured.keys():
        hot, cold = streams["hot_in"], streams["cold_in"]
        measured.update(
            hot_in_T=hot.T,
            cold_in_T=cold.T,
            m_dot_hot=hot.m_dot,
            m_dot_cold=cold.m_dot,
            cp_hot=hot.fluid.properties(hot.p, hot.T).cp_l,
            cp_cold=cold.fluid.properties(cold.p, cold.T).cp_l,
        )
    return inputs, streams, measured


def health_or_unavailable(module, result, measured):
    """Keep lack of a diagnostic model distinct from assessed nominal health."""
    health = module.health(result.outputs, measured)
    return (
        health
        if health is not None
        else Health(
            score=1,
            alarm=False,
            assessed=False,
            message="No diagnostic model or sufficient measurements",
        )
    )


class BindingPlan:
    """Resolve module objects and column units once for the entire run."""

    def __init__(self, plant, dataset, kind, only=None, on_error="record"):
        """Compile active bindings; root defaults permit minimal assumed-input profiles."""
        from gemini.core.types.bindings import Binding, ModuleBindings

        self.entries, self.columns = [], set()
        self.on_error = on_error
        self.skips, self.errors = {}, []
        if only is not None:
            for path in only:
                plant.get_submodule(path)
                if path not in plant.bindings:
                    raise ValueError(f"{path}: no measured boundary bindings")
        bindings = plant.bindings
        if kind == "simulate":
            bindings = {
                "": bindings.get(
                    "",
                    ModuleBindings(
                        inputs={
                            name: Binding(column=name, unit=info.unit)
                            for name, info in dataset.columns.items()
                        }
                    ),
                )
            }
        for path, original in bindings.items():
            if kind != "simulate" and (not path or only is not None and path not in only):
                # Standalone equipment may use root bindings for measured replay.
                if path or plant._children or only is not None and path not in only:
                    continue
            bound = original.model_copy(deep=True)
            module = plant.get_submodule(path)
            for group in [bound.inputs, bound.measured, bound.state, *bound.streams.values()]:
                for field, binding in list(group.items()):
                    if (
                        kind == "simulate"
                        and group is bound.inputs
                        and binding.column not in dataset.names
                    ):
                        if _nested_get(plant.boundary.get("root_inputs", {}), field) is not None:
                            del group[field]
                            continue
                    if binding.column in dataset.columns:
                        binding.unit = dataset.columns[binding.column].unit
                    self.columns.add(binding.column)
            defaults = plant.boundary.get("stream_defaults", {}).get(path)
            self.entries.append((path, module, bound, defaults))
        missing = sorted(self.columns - set(dataset.names))
        if missing:
            raise ValueError("Dataset is missing bound columns: " + ", ".join(missing))


def _nested_get(mapping, path):
    for part in path.split("."):
        if not isinstance(mapping, dict) or part not in mapping:
            return None
        mapping = mapping[part]
    return mapping


def _nested_set(mapping, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        mapping = mapping.setdefault(part, {})
    mapping[parts[-1]] = value


def twin_step(plant, sample, states, plan):
    """Evaluate measured boundaries, taking measured state or advancing retained state."""
    plant.apply_params_at(sample.t)
    results = {}
    plan.skips, plan.errors = {}, []
    for path, module, bound, defaults in plan.entries:
        try:
            inputs, streams, measured = prepare(module, bound, sample.row, defaults)
            if module.stateful:
                state = (
                    {key: _value(sample.row, binding) for key, binding in bound.state.items()}
                    if bound.state
                    else deepcopy(states[path]) if path in states else module.initial_state()
                )
                next_state, prediction = module.step(state, inputs, streams, sample.dt)
            else:
                prediction = module(inputs, streams)
            results[path] = prediction, health_or_unavailable(module, prediction, measured)
            if module.stateful:
                states[path] = state if bound.state else next_state
        except MissingMeasurement as exc:
            plan.skips.setdefault(path, Counter())[str(exc)] += 1
        except Exception as exc:
            groups = {
                "inputs": bound.inputs,
                **{f"streams.{port}": fields for port, fields in bound.streams.items()},
            }
            boundary = ", ".join(
                f"{section}.{field}={sample.row.get(binding.column)!r} {binding.unit}"
                for section, fields in groups.items()
                for field, binding in fields.items()
            )
            message = f"{module.path}: {exc}; boundary: {boundary}"
            if plan.on_error == "raise":
                raise ValueError(message) from exc
            plan.errors.append(dict(module=path, message=message, type=type(exc).__name__))
    return results


def chained_step(plant, sample, states, plan):
    """Apply root bindings to a single plant call, preserving the handwritten wiring."""
    plant.apply_params_at(sample.t)
    plan.skips, plan.errors = {}, []
    _, _, bound, defaults = plan.entries[0]
    inputs = deepcopy(plant.boundary.get("root_inputs", {}))
    values, streams, _ = prepare(plant, bound, sample.row, defaults)
    for field, value in values.items():
        _nested_set(inputs, field, value)
    # Nested Stream controls (such as the secondary inlet) use their own fluid density.
    for field, binding in bound.inputs.items():
        if field.endswith(".m_dot") and binding.unit in ("m3/h", "m3/s"):
            prefix = field.rsplit(".", 1)[0]
            raw = _nested_get(inputs, prefix)
            stream = Stream.model_validate(raw)
            _nested_set(
                inputs, field, stream.m_dot * stream.fluid.properties(stream.p, stream.T).density
            )
    if any(module.stateful for module in plant.modules()):
        states[""], result = plant.step(
            states.get("", plant.initial_state()), inputs, streams, sample.dt
        )
    else:
        result = plant(inputs, streams)
    return {
        path: (child, health_or_unavailable(plant.get_submodule(path), child, {}))
        for path, child in result.leaves().items()
    }
