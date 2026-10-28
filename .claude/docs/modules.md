# Writing modules

GEMINI modules follow the same ownership model as `torch.nn.Module`: declarations and child
modules are assigned once in `__init__`; `Module` registers them; `forward` receives plain
values; computed outputs are assigned; and only flows are returned.

```python
import gemini as gm
from gemini.core.types import (
    Control, Inlet, Outlet, Output, Parameter,
    PowerFlow, Pressure, PressureDifference, Stream,
)

class Pump(gm.modules.Module):
    """Raise a stream's pressure by a controllable amount."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.efficiency = Parameter(float, default=0.8, gt=0, le=1)

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.pressure_setpoint = Control(PressureDifference)

        # Outputs
        self.discharge_pressure = Output(Pressure, soft_sensor=True)

        # Outlets
        self.discharge = Outlet(Stream)
        self.electricity = Outlet(PowerFlow)

    def forward(self, suction, pressure_setpoint):
        discharge = suction.with_(p=suction.p + pressure_setpoint)
        self.discharge_pressure = discharge.p
        return {"discharge": discharge, "electricity": PowerFlow(P=0)}
```

Instantiate values as keywords: `Pump(efficiency=0.9)`. Numbers are SI; unit strings and
`gm.Quantity` are converted at the public boundary. A required parameter without a default is
uninitialized until supplied, assigned or loaded. Read its metadata with `get_parameter`.

## Authoring rules

1. Declare everything in `__init__` with `Parameter`, `Inlet`, `Control`, `Boundary`, `Output`
   or `Outlet`. Assign child modules there too. Never repeat derived metadata or port lists.
2. Use section comments in this order: `# Modules`, `# Parameters`, `# Inlets`, `# Controls`,
   `# Boundaries`, `# Outputs`, `# Outlets`. Omit empty sections and separate sections by one
   blank line.
3. A `Control` is a command that an optimiser or agent may change. A `Boundary` is imposed by
   the world. `inputs()` returns controls plus boundaries.
4. `forward` arguments must exactly match declared inlets, controls and boundaries. The first
   call checks this contract and reports missing or extra names.
5. Assign every required output during `forward`; return outlets as a name-to-flow dictionary.
   A module with one outlet may return that flow directly. Results expose only `out.outputs`
   and `out.outlets`; they are not tuple-unpackable.
6. Value-bearing `__init__` arguments are forbidden. Only structural arguments that change the
   module tree are allowed. Values come from keyword construction, assignment, state loading or
   the legacy bridge; defaults live in declarations.
7. `Module` derives `name`, `description`, `category`, ports, input contracts, soft sensors and
   calibratable parameters. Do not declare any of those twice.

## Plants and containers

Plants build their children themselves. `ModuleList` registers numeric child paths,
`ModuleDict` registers caller-provided keys, and `Sequential` chains children with one fluid
inlet and outlet. `DoubletHeatPlant` therefore owns `filters.hot` and `filters.cold`; callers
load values into this fixed tree rather than injecting children.

`named_modules`, parameters, state dictionaries, save/load, hooks, bindings and engine paths all
traverse registered containers. Pre-hooks receive `(module, inputs, inlets)` and post-hooks also
receive the immutable `ModuleResult`. Dated parameter snapshots remain available through
`params_at`, `apply_params_at` and `param_history`; each `Parameter` also owns validated history
metadata.

Energy use is reported with `PowerFlow`, `FuelFlow` and `HeatFlow` outlets. Fluid energy remains
on `Stream`. Health models consume recorded output values; missing diagnostic evidence remains
explicitly unassessed.
