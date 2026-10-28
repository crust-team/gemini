"""Independent equipment evaluation on measured boundaries, with explicit missing-data skips."""

import math
from collections import Counter

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


def apply_dated_params(plant, at):
    """Apply a new dated snapshot once while retaining explicitly applied calibrations."""
    for name, item in plant.config.modules.items():
        snapshot = item.at(at)
        if plant._active_snapshots.get(name) != snapshot.valid_from:
            module = plant.get_submodule(name)
            values = snapshot.params | plant._parameter_overrides.get(name, {})
            module.params = module.Params.model_validate(values)
            module.fluid = module._resolve_fluid()
            plant._active_snapshots[name] = snapshot.valid_from


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


def evaluate(plant, row, at):
    """Evaluate bound equipment independently; count missing measurements by module and reason."""
    apply_dated_params(plant, at)
    result = {}
    defaults = plant.config.boundary.get("stream_defaults", {})
    for path, bindings in plant.config.bindings.items():
        module = plant.get_submodule(path)
        try:
            inputs, streams, measured = prepare(module, bindings, row, defaults.get(path))
        except MissingMeasurement as exc:
            counter = plant.skip_counts.setdefault(path, Counter())
            counter[str(exc)] += 1
            continue
        prediction = module(inputs, streams)
        result[path] = prediction, health_or_unavailable(module, prediction, measured)
    return result


def scenario_inputs(plant, row):
    """Translate bound observations into this handwritten plant's public operating controls."""
    controls, streams = {}, {}
    defaults = plant.config.boundary.get("stream_defaults", {})
    for path, bindings in plant.config.bindings.items():
        module = plant.get_submodule(path)
        values, inlet, _ = prepare(
            module, bindings.model_copy(update={"measured": {}}), row, defaults.get(path)
        )
        controls[path], streams[path] = values, inlet
    if plant.name != "geothermal_example":
        raise ValueError("scenario_inputs needs an explicit adapter for this plant type")
    return (
        dict(
            m_dot=controls["doublet.reservoir"]["m_dot"],
            esp_frequency=controls["doublet.esp"]["frequency"],
            injection_pressure=controls["injection_pump"]["discharge_pressure"],
            injection_frequency=controls["injection_pump"].get("frequency", 60),
            secondary=streams["heat_exchanger"]["cold_in"],
        ),
        {},
    )
