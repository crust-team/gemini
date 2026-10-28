# Writing modules

Subclass `core.modules.module.Module`; declare a unique registry name, category, description and
honest fidelity. Nested Pydantic `Params`, `Inputs`, `Outputs` use physical quantity aliases.
Design parameter models are frozen. Ports are mappings from names to Stream, PowerFlow, FuelFlow
or HeatFlow types. Both direct forward and `__call__` validate port sets and types; call the
module normally so hooks and audit capture run.

```python
from pydantic import BaseModel, Field
from gemini.core.modules.module import Module
from gemini.core.types import ModuleResult, PressureDifference, Stream

class Restriction(Module):
    name, category = "restriction", "treatment"
    inlets, outlets = {"inlet": Stream}, {"outlet": Stream}

    class Params(BaseModel):
        dp: PressureDifference = Field(1000, ge=0, description="Pressure loss [Pa]")

    def forward(self, inputs, streams_in):
        inlet = streams_in["inlet"]
        return ModuleResult(self.Outputs(), {"outlet": inlet.with_(p=inlet.p-self.params.dp)})
```

## Handwritten plants

Assigning `self.pump = pump` registers a child. `__init__` builds the module tree and `forward`
writes each connection explicitly, exactly as a composable model. No GraphPlant, topology
builder, link schema or stream-tearing solver remains. `Sequential` chains one-fluid-inlet,
one-fluid-outlet modules; energy reports remain in its captured child results.

`Doublet` owns reservoir, lower well, ESP, riser, injection well and receiving reservoir.
Its `forward` accepts an independently specified return stream. When surface equipment connects
supply to return within the same call, `GeothermalExamplePlant.forward` explicitly schedules
`doublet.produce`, surface equipment, then `doublet.inject`. These two limb methods invoke every
equipment child through `__call__`; all leaf hooks, paths and result captures remain available.
The grouping object's own forward hook runs only when calling Doublet as a whole.

`GeothermalExamplePlant.Inputs` contains production mass flow, ESP frequency, injection pressure,
optional injection frequency, and a secondary inlet Stream. Outputs contain delivered heat,
total electricity and COP (None for zero consumption). It follows the diagram's actual order:
production -> degasser -> hot filter -> HX -> return filter -> injection pump -> injection.

Plants serialize themselves with `to_dict`/`from_dict` and `save`/`load`; the file records
importable classes, histories, bindings and fluids but never runtime wiring. `trace_wiring`
observes real Stream identities through temporary hooks and cleans up on failure. Old diagram
translation and wiring comparison live exclusively in `gemini.legacy`.

## Reporting energy and diagnostics

Energy ports are outlets computed by forward; callers never supply electricity or fuel:
`electricity: PowerFlow` reports grid draw, `fuel: FuelFlow` reports LHV draw,
`heat_loss: HeatFlow` reports environmental release. Fluid streams carry inter-equipment heat.

ESP reports shaft power / motor efficiency (default 1). InjectionPump reports its predicted
power. Boiler always declares both electricity and fuel, zeroing the unused one, plus conversion
heat loss. Wells report signed m_dot*cp*(Tin-Tout) using the external flow sign. HX has two fluid
sides and no environmental-loss model. Filter, degasser, booster and blowdown add no energy
ports; the latter two have no modeled power consumption. See [types](types.md) for strict versus
thermal energy balances and the retained pump-model limitation.

`soft_sensors` identifies predicted fields; `calibratable` identifies fit parameters. Health
without sufficient diagnostics is `assessed=False`. Explicit source-data disagreements remain
visible; never suppress alarms or fabricate power to meet a reconciliation target.
Corrosion reads Fluid composition when separate measured gas chemistry is omitted.

## State and observers

`named_modules`, `get_submodule`, recursive parameter APIs, `apply`, state dictionaries and costs
traverse the registered tree. State dictionaries include validated Params and Fluid values.
Strict state loading checks paths/types and validates all entries before applying changes.
Pre-hooks receive `(module, inputs, streams_in)`; post-hooks additionally receive ModuleResult.
Hook handles remove their own registration. `EventLog.attach` observes the whole tree.
`last_results` exposes leaf results by relative path; `result.children` retains nested evaluation
structure. Results remain unpackable into `(outputs, streams)`.

Stateless `step` calls forward. Stateful equipment implements `initial_state` and
`step(state, inputs, streams_in, dt)` with state passed explicitly. Sequential advances nested
stateful children and captures the same hooks/result tree as ordinary calls. Custom stateful
plants must implement their own explicit stepping schedule.

## Plant-owned run configuration

Modules own sensor bindings, parameter histories and explicit overrides. Root bindings use the
empty path. `params_at(t)` validates dated selections; `apply_params_at(t)` recursively applies
changed snapshots without erasing explicit fits. Scalar display uses quantity metadata through
`extra_repr()`; classes may override it. Save preserves composite and leaf histories as well as
current state. Use `gm.load_plant`, `plant.save`, and the engine methods described in [API](api.md).
