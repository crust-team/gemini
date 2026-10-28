"""Chained plant scenarios driven by explicitly assumed operating conditions."""

from copy import deepcopy

from gemini.core.engine.results import Results
from gemini.core.modes.twin import health_or_unavailable
from gemini.core.types.profile import Profile


def run(plant, inputs_per_step, dt, *, base_inputs=None):
    """Run assumptions with reserved streams_in and optional timestamp keys per step."""
    if dt <= 0:
        raise ValueError("dt must be positive [s]")
    if isinstance(inputs_per_step, dict):
        inputs_per_step = _profile_steps(inputs_per_step, base_inputs or {})
    results = Results()
    state = plant.initial_state()
    for index, values in enumerate(inputs_per_step):
        values = dict(values)
        streams = {
            key: plant.inlets[key].model_validate(value)
            for key, value in values.pop("streams_in", {}).items()
        }
        at = values.pop("timestamp", index * dt)
        if any(m.stateful for m in plant.modules()):
            state, _ = plant.step(state, values, streams, dt)
        else:
            plant(values, streams)
        results.append(
            at,
            {
                path: (result, health_or_unavailable(plant.get_submodule(path), result, {}))
                for path, result in plant.last_results.items()
            },
        )
    return results


def _profile_steps(profiles, base_inputs):
    """Map dotted control paths to aligned profile samples; require explicit resampling."""
    if not profiles or not all(isinstance(p, Profile) for p in profiles.values()):
        raise ValueError("Expected a nonempty mapping of Profile inputs")
    index = next(iter(profiles.values())).index
    if any(p.index != index for p in profiles.values()):
        raise ValueError("Scenario profiles must share the same index; resample explicitly")
    for at in index:
        values = deepcopy(base_inputs)
        for path, profile in profiles.items():
            target = values
            parts = path.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = profile.at(at)
        yield values | {"timestamp": at}
