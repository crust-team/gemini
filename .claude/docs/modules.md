# Writing modules

An equipment module lives in `gemini/core/modules/<category>/<name>.py`. Subclass `Module`,
declare a unique registry name, category, description and fidelity (`model`, `simple` or
`passthrough`). `Params` holds validated design data; `Inputs` holds controls; `Outputs` holds
predicted quantities. Ports carry immutable `Stream` values. Each Pydantic field documents its
physical dimension. The built-in empty schemas are suitable for composites.

Implement `forward(inputs, streams_in) -> ModuleResult` without I/O or hidden process state.
Check mass and energy balance and reject invalid physical operating conditions. Stateless
`step` calls forward; stateful equipment overrides `initial_state` and
`step(state, inputs, streams_in, dt) -> (new_state, ModuleResult)`.

```python
from pydantic import BaseModel, Field
from gemini.core.modules import Module, ModuleResult

class Restriction(Module):
    name = "restriction"
    category = "treatment"
    description = "A specified pressure loss without heat transfer."
    fidelity = "simple"
    inlets = ("inlet",)
    outlets = ("outlet",)
    soft_sensors = ("pressure_drop",)
    calibratable = ("dp",)

    class Params(BaseModel):
        dp: float = Field(1000, ge=0, description="Pressure loss [Pa]")

    class Outputs(BaseModel):
        pressure_drop: float = Field(..., description="Pressure loss [Pa]")

    def forward(self, inputs, streams_in):
        stream = streams_in["inlet"].with_(p=streams_in["inlet"].p-self.params.dp)
        return ModuleResult(self.Outputs(pressure_drop=self.params.dp), {"outlet": stream})
```

## Composition and observation

Assigning `self.pump = pump` registers a child. `add_module` also supports named registration.
`named_modules`, `get_submodule`, `named_params`, `calibratable_params`, `set_param`, `apply`,
`state_dict` and `load_state_dict` traverse the same tree. State loading validates every matching
entry before applying changes. Non-strict loading ignores absent/extra paths, but still rejects
type mismatches and invalid parameters. Equality and hashing retain object identity.

`Sequential` chains equipment with one inlet and one outlet. Its controls are keyed by child
name or positional string index. `GraphPlant` derives unconnected boundary ports, routes
streams through validated links, and tears feedback edges until pressure, temperature and mass
residuals converge. `last_results` and `last_link_streams` expose the most recent evaluation.
The imported buried ESP has separate below-pump and riser nodes using the same well model.

Pre-hooks receive `(module, inputs, streams_in)`; post-hooks additionally receive `result`.
Hook handles remove only their own registration. `EventLog.attach` observes the whole tree.
Do not use direct forward calls when event traces are required.

## Twins and fidelity

Bindings belong in `core.config`: raw columns, raw dimensions, inlet conditions and measured
outputs. Historical twins evaluate each bound module on measured inlet conditions; scenarios
propagate predictions through the graph. Unbound equipment runs in scenarios only.

`soft_sensors` names predicted fields; `calibratable` names fit parameters. Implement `health`
when measurements support a diagnostic. `Health.assessed=False` explicitly denotes an absent
diagnostic model or insufficient evidence; a zero alarm flag alone does not establish health.
`health_report` collects available diagnostics recursively. Add `capex` only with a source.

Fidelity must be honest. The liquid-only degasser has zero gas flow, and booster/blowdown
passthroughs expose `modelled=False`. The injection pump uses supplied curves when available;
otherwise its pressure setpoint and efficiency determine hydraulic power.
