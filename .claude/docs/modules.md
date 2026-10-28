# Writing modules

GEMINI modules follow a fluid-first call contract. Child modules and declarations are assigned
once in `__init__`. `forward` receives exactly the declared fluid inlets and returns exactly the
declared fluid outlets. Controls and boundaries are applied by the base class and read from
`self`. Outputs are computed only after the fluid step succeeds.

## Leaf modules

Leaves declare ordinary `Output(kind)` values and implement `_compute_outputs`. The callback
requests any inlet or outlet it needs by parameter name; its signature is inspected and cached
when the class is defined. It never needs `super()._compute_outputs()`.

```python
from gemini.core.modules import Module
from gemini.core.physics import pumps
from gemini.core.types import (
    Control, Count, Frequency, Inlet, Outlet, Output, Parameter, Power, PressureDifference,
    Stream, VolumeFlow,
)


class Pump(Module):
    """Example fluid pump."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.no_stages = Parameter(Count)
        self.head_coeff = Parameter(list[float], shape=(6,))
        self.power_coeff = Parameter(list[float], shape=(6,))

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.flow = Output(VolumeFlow)
        self.head = Output(PressureDifference)
        self.power = Output(Power)
        self.electricity = Output(Power)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, suction):
        """Raise the suction pressure."""

        # Outlets
        flow = suction.volumetric_flow()
        head = pumps.head(flow, self.frequency, self.no_stages, self.head_coeff)
        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, suction, discharge):
        self.flow = suction.volumetric_flow()
        self.head = discharge.p - suction.p
        self.power = pumps.power(
            self.flow, self.frequency, self.no_stages, self.power_coeff
        )
        self.electricity = self.power
```

Derive pressure rise, duty, temperature change and similar outputs from inlet/outlet states when
that preserves the model's numerical contract. If both phases need an expensive intermediate,
put the calculation in a small private helper used by both; do not cache call data on `self`.
Every declared output, including an optional output whose value is `None`, must be assigned on
every output-enabled call.

## Composite modules

Composites never override `_compute_outputs`. They declare formula outputs in declaration order:

- `Output.of("child.path.output")` copies one descendant output from this call. Outlet fields,
  such as `Output.of("degasser.gas.m_dot")`, are also supported. The descendant must be called
  exactly once.
- `Output.total("electricity")` sums that additive output over all descendant leaf calls. A leaf
  called twice contributes twice. All declarations must have the same unit.
- `Output.ratio("thermal_power", "electricity_use")` divides earlier outputs on the same module
  and records `None` when the denominator is zero.

```python
class HeatPlant(Module):
    """Example composite plant."""

    def __init__(self):
        super().__init__()

        # Modules
        self.heat_exchanger = HeatExchanger()
        self.pump = Pump()

        # Inlets
        self.primary = Inlet(Stream)
        self.secondary = Inlet(Stream)

        # Outputs
        self.thermal_power = Output.of("heat_exchanger.duty")
        self.electricity_use = Output.total("electricity")
        self.cop = Output.ratio("thermal_power", "electricity_use")

        # Outlets
        self.secondary_out = Outlet(Stream)

    def forward(self, primary, secondary):
        """Evaluate children in physical flow order."""

        # Modules
        pumped = self.pump(suction=primary)
        exchanged = self.heat_exchanger(
            hot_in=pumped.outlets.discharge, cold_in=secondary
        )

        # Outlets
        secondary_out = exchanged.outlets.cold_out

        outlets = dict(secondary_out=secondary_out)
        return outlets
```

Formula paths are checked once the tree is complete and typo errors include a close-match
suggestion. `module.is_leaf` is true exactly when the module has no registered children.

## Call order and hooks

One call performs these steps:

1. validate inlets and apply controls/boundaries;
2. run forward pre-hooks;
3. run `forward` and validate its fluid outlet dictionary;
4. run leaf `_compute_outputs`;
5. evaluate composite formula outputs in declaration order;
6. run forward hooks;
7. verify every output was assigned and build `ModuleResult`.

Pre-hooks remain `hook(module)`. Register a forward hook with explicit names, for example:

```python
def observe(module, suction, discharge):
    print(module.head, suction.p, discharge.p)


handle = pump.register_forward_hook(observe)
```

Hook return values are ignored. Invalid hook parameter names fail at registration. Remove a hook
with `handle.remove()`.

## Skipping outputs

`gm.no_outputs()` is a nestable, context-local context manager and decorator. It skips
`_compute_outputs`, formulas, forward hooks and output completeness checks. Fluid forwarding,
pre-hooks and outlet validation still run; the result has an empty `outputs` mapping.

```python
with gm.no_outputs():
    fast = plant(secondary=stream)

assert dict(fast.outputs) == {}
```

## Structure

Constructor sections are ordered `Modules`, `Parameters`, `Inlets`, `Controls`, `Boundaries`,
`States`, `Outputs`, `Outlets`, with empty sections omitted. `forward` uses only `# Modules` on
composites and `# Outlets` when outlets exist. It contains no `self.<name> = ...` assignments and
ends with `outlets = dict(...)` followed by `return outlets`. Method order is `__init__`,
`forward`, `_compute_outputs`, then private helpers.

Inlets and outlets accept `Stream` types only. Electricity, fuel use and environmental heat loss
are `Power` outputs. Results keep the same dotted `<module path>.<name>` addressing scheme.
