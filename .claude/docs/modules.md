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
        """Raise suction pressure and report the discharge."""

        # Outputs
        self.discharge_pressure = suction.p + pressure_setpoint

        # Outlets
        discharge = suction.with_(p=self.discharge_pressure)
        electricity = PowerFlow(P=0)

        outlets = dict(discharge=discharge, electricity=electricity)
        return outlets
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
5. Assign every required output during `forward`; return every outlet in an explicit dictionary,
   including modules with zero or one outlet. Results expose only `out.outputs` and
   `out.outlets`; they are not tuple-unpackable.
6. Value-bearing `__init__` arguments are forbidden. Only structural arguments that change the
   module tree are allowed. Values come from keyword construction, assignment, state loading or
   the legacy bridge; defaults live in declarations.
7. `Module` derives `name`, `description`, `category`, ports, input contracts, soft sensors and
   calibratable parameters. Do not declare any of those twice.

## Fixed forward structure

Every `forward` uses plain section comments in this order, omitting empty sections:

1. `# Modules` contains only child-module calls and result unpacking. Only composites use it.
2. `# Outputs` performs every `self.<output> = ...` assignment. Shared calculations are done
   once here and reused by outlets.
3. `# Outlets` creates one local per declared outlet, named exactly like the declaration.
4. The final statements are `outlets = dict(...)` in declaration order and `return outlets`.

Leaf template:

```python
def forward(self, suction, frequency):
    """Compute pump head and raise the suction pressure."""

    # Outputs
    self.flow = suction.volumetric_flow()
    self.head = pumps.head(self.flow, frequency, self.no_stages, self.head_coeff)
    self.discharge_pressure = suction.p + self.head

    # Outlets
    discharge = suction.with_(p=self.discharge_pressure)
    electricity = PowerFlow(P=self.power)

    outlets = dict(discharge=discharge, electricity=electricity)
    return outlets
```

Composite template:

```python
def forward(self, secondary, m_dot, esp_frequency, injection_pressure, injection_frequency):
    """Connect the doublet limbs through the surface equipment."""

    # Modules
    supply, esp_power, production_heat = self.doublet.produce(m_dot, esp_frequency)
    degassed = self.degasser(inlet=supply)
    exchanged = self.heat_exchanger(
        hot_in=degassed.outlets.liquid,
        cold_in=secondary,
    )

    # Outputs
    self.thermal_power = exchanged.outputs.duty
    self.electricity_use = esp_power.P
    self.cop = self.thermal_power / self.electricity_use if self.electricity_use else None

    # Outlets
    secondary_out = exchanged.outlets.cold_out
    gas = degassed.outlets.gas
    electricity = PowerFlow(P=self.electricity_use)
    heat_loss = production_heat

    outlets = dict(
        secondary_out=secondary_out,
        gas=gas,
        electricity=electricity,
        heat_loss=heat_loss,
    )
    return outlets
```

Private helpers may shorten calculations, but declared outputs remain visibly assigned in the
`# Outputs` section. Stateful `step` overrides use the same section vocabulary while retaining
the engine's `(state, result)` return contract.

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
