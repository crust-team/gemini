# Writing a Component

A component is one piece of plant equipment (pump, well, heat exchanger, ...). It lives in
`gemini/components/<category>/<name>.py` and contains only physics and monitoring logic specific
to that equipment.

## Checklist

1. Subclass `gemini.core.base.component.Component`.
2. Set `name` (unique snake_case), `category` (folder name) and a one-sentence `description`.
   The registry and the AI agent read these.
3. Declare ports: `inlets` and `outlets` as tuples of port names. Ports carry `Stream` objects.
   Flow, temperature and pressure arrive through inlet streams, not as separate inputs.
4. Define three nested Pydantic models:
   - `Params`: fixed design data (stages, curves, UA, geometry). Validated once at construction.
   - `Inputs`: per-step operating inputs that are not streams (frequency, setpoints).
   - `Outputs`: per-step results.
   Every field has `description="... [unit]"` and constraints (`gt`, `ge`, `min_length`) where
   physics demands them.
5. Implement `compute(inputs, streams_in) -> (outputs, streams_out)`. It must be pure: no I/O,
   no database, no global state, same inputs give the same outputs.
6. Stateful equipment (storage, slowly depleting reservoir) sets `stateful = True` and
   implements `initial_state()` and `step(state, inputs, streams_in, dt)`.
7. Twin hooks, when meaningful:
   - `soft_sensors`: `Outputs` fields that replace missing measurements.
   - `calibratable`: `Params` fields history matching may fit.
   - `health(predicted, measured) -> Health`: compare prediction with measurement, return a
     score in [0, 1], an alarm flag and a short message. Thresholds are `Params` fields with
     sensible defaults, not constants in the code.
8. Optional `capex()` when a cost correlation exists; cite the source.
9. Generic physics (pipe flow, heat loss, heat-exchanger effectiveness, corrosion, erosion,
   fluid properties, unit conversion) is imported from `gemini.core.physics`, never copied into
   the component.
10. Add a mapper in `core/plant/param_mapping.py` if the component appears in GEMINI `.param`
    files.
11. Add `tests/components/<category>/test_<name>.py` (see testing.md).

## Do not

- Import another component. Chains of components are built by the engine or by the caller.
- Put sensor tag names, file paths or database access in a component.
- Create a component file before the equipment is actually modelled or placed in a plant.
- Add helper modules next to a component; shared code belongs in `core/physics`.

## Skeleton

```python
"""Heat pump component.

Raises the temperature of the secondary loop using electricity.
Reference: <source>.
"""

from pydantic import BaseModel, Field

from gemini.core.base.component import Component
from gemini.core.base.stream import Stream


class HeatPump(Component):
    """Electric compression heat pump."""

    name = "heatpump"
    category = "heat"
    description = "Electric heat pump that lifts low-temperature heat to supply temperature."
    inlets = ("source_in", "sink_in")
    outlets = ("source_out", "sink_out")
    soft_sensors = ("cop",)
    calibratable = ("carnot_efficiency",)

    class Params(BaseModel):
        capacity: float = Field(..., gt=0, description="Nominal heating capacity [W]")
        carnot_efficiency: float = Field(0.5, gt=0, le=1, description="Fraction of Carnot COP [-]")

    class Inputs(BaseModel):
        supply_T: float = Field(..., gt=0, description="Sink outlet setpoint [K]")

    class Outputs(BaseModel):
        heat: float = Field(..., description="Heat delivered to the sink [W]")
        power: float = Field(..., description="Electric power [W]")
        cop: float = Field(..., description="Coefficient of performance [-]")

    def compute(self, inputs, streams_in):
        ...
```
