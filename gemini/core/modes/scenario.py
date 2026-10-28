"""Chained plant scenarios driven by explicitly assumed operating conditions."""

from gemini.core.engine.results import Results
from gemini.core.modes.twin import health_or_unavailable
from gemini.core.types.flows import Stream


def run(plant, inputs_per_step, dt):
    """Run assumptions with reserved streams_in and optional timestamp keys per step."""
    if dt <= 0:
        raise ValueError("dt must be positive [s]")
    results = Results()
    state = plant.initial_state()
    for index, values in enumerate(inputs_per_step):
        values = dict(values)
        streams = {
            key: Stream.model_validate(value) for key, value in values.pop("streams_in", {}).items()
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
