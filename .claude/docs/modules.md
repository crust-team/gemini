# Writing modules

GEMINI modules follow a fluid-first call contract. Child modules and declarations are assigned
once in `__init__`. Every `forward` receives the same read-only `Ports` mapping and returns a
dictionary containing exactly the declared fluid outlets. Controls and boundaries are applied by
the base class and read from `self`. Outputs are computed only after the fluid step succeeds.

Write a module with `Module` from `gemini.modules` (also `gm.modules.Module`) and the
declarations from `gemini.types`. The base class has no string catalogue, sequential
container, fidelity flag or cost method. The shipped equipment, with each model's ports, parameters, equations and energy-audit status, is
listed in [equipment.md](equipment.md); its classes are good references for new modules.

**Physics lives only in `gemini/physics/`.** Modules declare and wire; they never define physics.
Reuse existing physics functions wherever possible and combine them; add a new physics function
only when nothing existing can do the job, and generalise an existing one rather than writing a
second copy. Never write a formula inside a module, and never write the same formula twice.
Fitting and calibration belong in `gm.analysis` or `gm.optim`, not in modules.

## Construction and metadata

Construct a module without arguments and set its values afterwards; `update_params` returns the
module, so `ESP().update_params(stage_count=12, ...)` builds a configured pump. Only structural
tree-shape arguments (for example `ModuleList(modules)`) go to `__init__`. There is no
class-creation hook: `module.name` is the snake_case class name computed on access,
`Module.help()` reads the first paragraph of the class docstring and lists the declarations, and
any number of classes may share a name. `module.path` is the dotted position in the tree, or the
name for a standalone module. `module.fluid` is a validated property saved by `state_dict()`. Plant files
and checkpoints store the root class as `module:qualname` through `class_path`/`import_class` in
`module.py`, the only import-by-string in the package.

## Registry, categories and streams

`gemini/modules/registry.py` is the one registry of module and plant types. A class joins it
under its class name with `gm.modules.register(cls)`, and every shipped equipment class is
registered when `gm.modules` is imported. `gm.modules.names(category=None)`, `get(name)` and
`categories()` read it; an unknown name raises `ValidationError` with its close matches in
`suggestions`.

`gm.modules.load_file(path)` imports a Python file, registers every `Module` class it defines that
states a `category` (a base class without one is skipped) and returns their names, so a new module
can join a plant spec by `type`. It executes the file; a file that does not import, or defines no
such class, raises `ValidationError` (code `invalid_format` or `invalid_value`), and a name that is
already taken by another class is refused.

Before registering a new class, run `gm.testing.check_module(cls, example=None)`. It never raises
and returns `{module, passed, checks}`, each check `{name, passed, message}` with `passed` `True`,
`False` or `None` (undecided). The checks are `is_module`, `instantiate` (the declaration rules
run in `__init__`), `category`, `forward_signature` (exactly `forward(self, inlets)`), `units`
(every scalar numeric parameter, control, boundary and output is declared with a quantity type
that has a unit; coefficient arrays are exempt), `describe` (plain JSON) and `call` (one
`gm.evaluate` call). A module that needs parameters, controls or inlet streams is undecided on
`call` until `example` gives them in the shape of `gm.evaluate`:
`{"parameters": {...}, "inlets": {...}, "controls": {...}}`.

There is one classification: a shipped module's category is the name of the folder of
`gemini/modules/` that holds its file, and a new module goes in the folder of what it does.
`registry.CATEGORIES` is the fixed list of those folders, one word each, in display order;
[equipment.md](equipment.md#overview) lists the modules of each. `Module.category` reads the folder
from the import path of the class, so a shipped class never declares it and the two cannot disagree
(`tests/unit/modules/test_registry.py` checks the folders, the list and every class). A class
from outside (`register`, `load_file`) has no folder: it states the class attribute `category`, one
of the list, and a subclass of a shipped class states its own.

A port declares its stream type: `Inlet(Stream, stream="brine")`, one of `gm.streams.names()`.
A port without one, `stream=None`, takes whatever flows through it: piping, `CentrifugalPump`,
`HeatExchanger` and the source side of `HeatPump`. Stream types never change a calculation; they
say what may be connected.

## Describing a module

`Module.describe()`, `Module.parameter_schema()` and `Module.validate_params(params)` work on a
class (a new instance answers) or on an instance. They live in
`gemini/modules/description.py`, return plain JSON (`json.dumps(..., allow_nan=False)`) and
never change the module.

`describe()` returns `{name, type, category, summary, doc, parameters, controls, boundaries,
measured, state, inlets, outlets, outputs, children, connections, values}`:

- `name` is `module.path`, `type` the class name (a plant shows its given name), `summary` the
  first paragraph of the docstring and `doc` all of it.
- `parameters`, `controls`, `boundaries`, `measured` and `state` map a name to `{type, unit,
  quantity, default, minimum, maximum, enum, description, section}`. A missing item is `null`;
  `default` is `null` for `UNSET`. `minimum` and `maximum` are the closest limit, so a strict bound
  (`gt`, `lt`) shows as the bound itself. `enum` comes from a `Literal`. Only the module's own
  declarations are listed; children appear under `children`.
- `measured` lists every output of the module itself: replay (`engine/step.py`) takes a measured
  binding for any output name and compares it with that output; no narrower rule exists.
- `inlets` and `outlets` map a port to `{stream, fields: {m_dot: {unit: "kg/s"}, T: {unit: "K"},
  p: {unit: "Pa"}}}`; `stream` is `null` for a port that takes any stream.
- `outputs` maps a name to `{unit, kind, soft_sensor}`; `kind` is the additive quantity name
  (one of the nine) or `null`.
- `children` is `{name: type}` and `connections` is `[{source, target, stream, kind}]`, both empty
  for a leaf. A plant exposes its wiring through `_connection_list()`; a handwritten composite has
  none, because its wiring is code.
- `values` holds the current `parameters`, `controls` and `boundaries`; unset ones are left out
  and a child's values are keyed by dotted path. On a class they are the defaults of a new
  instance.

`parameter_schema()` is JSON Schema draft 2020-12: `$schema`, `title`, `type: object`,
`properties`, `required` (parameters with no default) and `additionalProperties: false`. A child's
parameters appear under their dotted path. Each property has the standard keywords (`type` or
`anyOf`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `enum`, `default`,
`description`) plus `unit` and `quantity`. A number with a unit is `anyOf` number and string,
because inputs accept `"150 m3/h"`.

`validate_params(params, on_error="raise")` checks every entry and raises one `ValidationError` that
carries every problem; with `on_error="record"` it returns them, each
`{path, code, message, suggestions}`. `path` is the parameter name; the codes are `unknown_name` (with `suggestions`),
`invalid_unit`, `out_of_bounds` and `invalid_value`. It runs `declaration.validate` once per entry
and tells the failures apart by the exception and its cause.

## Listing declarations

Every declaration listing takes `recurse` with default `True` and keys its result by dotted path
relative to the module (`"doublet.esp.frequency"` from the root): `parameters()` and
`named_parameters()` iterate, `calibratable_parameters()` returns a list, and `controls()`,
`boundaries()`, `inputs()`, `outputs()` and `soft_sensors()` return dicts. Pass `recurse=False`
for the module's own declarations under their local names. `inlets()` and `outlets()` take no
`recurse`: a child's ports are internal connections, not ports of the parent.
`children()`/`named_children()` list direct children and `modules()`/`named_modules()` walk the
tree. `get_parameter`, `get_control`, `get_boundary` and `get_submodule` resolve one dotted path
and suggest a close match for a typo.

## Leaf modules

Leaves declare ordinary `Output(kind)` values and implement
`_compute_outputs(self, inlets, outlets)`. It never needs `super()._compute_outputs()`.

```python
from gemini.modules import Module
from gemini.physics import pumps
from gemini.types import (
    Control, Count, Electricity, Frequency, Inlet, Outlet, Output, Parameter, Power,
    PressureDifference, Stream, VolumeFlow,
)


class Pump(Module):
    """Example fluid pump."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.stage_count = Parameter(Count)
        self.head_coefficients = Parameter(list[float], shape=(6,))
        self.power_coefficients = Parameter(list[float], shape=(6,))

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.flow = Output(VolumeFlow)
        self.head = Output(PressureDifference)
        self.power = Output(Power)
        self.electricity = Output(Electricity)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, inlets):
        """Raise the suction pressure."""

        # Outlets
        suction = inlets.suction
        flow = suction.volumetric_flow()
        head = pumps.head(flow, self.frequency, self.stage_count, self.head_coefficients)
        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        suction = inlets.suction
        discharge = outlets.discharge
        self.flow = suction.volumetric_flow()
        self.head = discharge.p - suction.p
        self.power = pumps.power(self.flow, self.frequency, self.stage_count, self.power_coefficients)
        self.electricity = self.power
```

Derive pressure rise, duty, temperature change and similar outputs from inlet/outlet states when
that preserves the model's numerical contract. If both phases need an expensive intermediate,
put the calculation in a small private helper used by both; do not cache call data on `self`.
Every declared output, including one whose value is `None`, must be assigned on every
output-enabled call.

## Composite modules

Composites declare formula outputs in declaration order and override `_compute_outputs` only to
record their own value for an additive output:

- `Output.of(self.child.output)` copies one descendant output from this call, for example
  `Output.of(self.heat_exchanger.duty)` or
  `Output.of(self.producers[0].riser.wellhead_temperature)`. An outlet field is referenced with
  `Outlet.field(name)`: `Output.of(self.degasser.gas.field("m_dot"))`. The descendant must be
  called exactly once, and the output adopts the target's kind.
- An output of an additive quantity declared without a formula, such as
  `self.electricity = Output(Electricity)`, is the automatic sum of the descendant leaf outputs
  with the same name over this call. A leaf called twice contributes twice; the sums of nested
  composites are not counted again. Every descendant leaf output of that name must have the same
  quantity and unit, and at least one must exist; otherwise the first call raises `DefinitionError`
  (with a close-match suggestion for a name no leaf declares). A composite that records its own
  value for the output in `_compute_outputs` replaces the sum. The additive quantities are listed
  in [types.md](types.md#quantities-and-declarations).
- `Output.ratio(self.thermal_power, self.electricity)` divides two earlier outputs of the same
  module and records `None` when either value is `None` or the denominator is zero.

- `Output.difference(self.first, self.second, kind)` subtracts two earlier outputs of the same
  module, as `kind`, and records `None` when either value is `None`.

Formulas take declaration references, not path strings. Children are assigned first
(`# Modules`), so the references exist when the outputs are declared. Assigning a formula checks
it while the class is built: an `Output.of` target outside the descendant tree (or a string), or a
ratio operand that is not an earlier output of the module, raises `DefinitionError`, an unknown
outlet field raises `ValidationError` with a close-match suggestion, and a misspelled reference
(`self.heat_exchanger.dutyy`, `self.heat_exchangerr.duty`) raises `ValidationError` with the
module path and the closest child, parameter, input, output, state or port (an `AttributeError`,
so `hasattr` stays false). The first call resolves each reference to its descendant
path by identity, so deep copies and nested trees resolve to their own children.

```python
from gemini.modules import HeatExchanger


class HeatPlant(Module):
    """Example composite plant."""

    def __init__(self):
        super().__init__()

        # Modules
        self.heat_exchanger = HeatExchanger()
        self.pump = Pump()

        # Inlets
        self.primary_in = Inlet(Stream)
        self.secondary_in = Inlet(Stream)

        # Outputs
        self.thermal_power = Output.of(self.heat_exchanger.duty)
        self.electricity = Output(Electricity)
        self.cop = Output.ratio(self.thermal_power, self.electricity)

        # Outlets
        self.secondary_out = Outlet(Stream)

    def forward(self, inlets):
        """Evaluate children in physical flow order."""

        # Modules
        pumped = self.pump(suction=inlets.primary_in)
        exchanged = self.heat_exchanger(
            hot_in=pumped.outlets.discharge, cold_in=inlets.secondary_in
        )

        # Outlets
        secondary_out = exchanged.outlets.cold_out

        outlets = dict(secondary_out=secondary_out)
        return outlets
```

`module.is_leaf` is true exactly when the module has no registered
children. Composites built from a variable number of children use the containers
`ModuleList(modules)` (children named `"0"`, `"1"`, ...; inserting or removing renumbers the later
children) and `ModuleDict(mapping)` (caller-chosen keys that must not shadow module or mapping
attributes). Containers compare and hash by identity like every module.

### A composite that sets its children's values

A composite may derive its children's parameters from its own. It overrides `set_params`, computes
the child values with functions from `gemini/physics/` and calls `super().set_params` with them:

```python
from gemini.modules import Module, ProductionReservoir
from gemini.physics import hydraulics
from gemini.types import Density, Length, Parameter


class Column(Module):
    """A reservoir whose pressure comes from the height of its water column."""

    def __init__(self):
        super().__init__()

        # Modules
        self.reservoir = ProductionReservoir()

        # Parameters
        self.height = Parameter(Length | None, default=None)
        self.density = Parameter(Density | None, default=None)

    def set_params(self, path, params, valid_from=None):
        """Derive the reservoir pressure, unless the same call states it."""
        if path:
            return super().set_params(path, params, valid_from)
        values = self._own_values(params, valid_from)
        derived = {}
        if values["height"] is not None and values["density"] is not None:
            pressure = hydraulics.hydrostatic_dp(values["density"], values["height"])
            derived["reservoir.pressure"] = pressure
        return super().set_params("", self._keep_derived(derived, params) | params, valid_from)
```

`_own_values(params, valid_from)` gives the module's own values in force at that date with the ones
of this call, in SI, so a dated call derives from the design of its date. A value that has not been
given yet derives nothing: the values may arrive one call at a time. `_keep_derived(derived, params)`
does the bookkeeping: an explicit child value in the call wins, now and in later calls
(`{"depth": "3000 m", "well.pipe_path": [...]}` keeps the given pipe path), and it records the names
it keeps.

Every route that sets parameters reaches this method: `add(..., params=)`, `from_dict`,
`set_params(path, ...)` at any depth, a dated `set_params(..., valid_from=)`, a `param_history`
section, `update_params` of an own parameter and attribute assignment. A fluid section is set
through the `fluid` property, which a composite that derives from its fluid overrides.

`to_dict` stores the module's own parameters and the explicit child values, never a derived value:
`from_dict(p.to_dict())` derives them again and rebuilds the same numbers. Dated entries of a child
that only hold derived values are left out in the same way.

### A composite with a closed circuit

A composite with a closed circuit inside one call (a substation's building loop) needs the
circulated temperature before its first child call. It iterates with trial passes:
`child.trial_outlets(inlets)` returns the outlets of a call that no running call records, with
outputs skipped and pre-hooks run, and refuses stateful modules. When the loop has converged
(`close_loop` in `gemini/modules/plants/loops.py`), the composite calls every child once, so
formulas and balances see exactly one call each. `child.start_states()` returns the states a call
of a stateful child would start from (its entry of the running step, else its initial states),
for a loop through a stateful child whose outlet depends only on its state.

## Values

Parameters, controls and boundaries are set by attribute assignment or in bulk:

- `update_params(**changes)` validates parameters by local or dotted path, records them as
  explicit overrides and returns the module; `clear_param_overrides()` forgets the overrides so
  values come from the dated snapshots in `param_history` alone; `params_at(at)` returns the
  values active at an instant and `apply_params_at(at)` applies them to the whole tree.
- `set_inputs(mapping)` persists validated controls and boundaries addressed by dotted path and
  returns the module; `module.frequency = 50` persists one value; `has_input_value(name)` says
  whether a control or boundary has a persisted value.
- `missing_parameters()` lists uninitialized parameters and `is_initialized` is true when there
  are none.
- `state_dict()` returns JSON-safe parameter values and the fluid of every module path, and
  `load_state_dict(state, strict=True)` validates all of them before applying any. With
  `strict=False` only the modules named in `state` are filled; unknown paths are always rejected.
  `to_dict()`/`from_dict()` and `save(path)`/`load(path)` add dated histories, overrides, bindings
  and boundary defaults.

```python
curve = [1, 0, 0, 0, 0, 0]
pump = Pump().update_params(stage_count=10, head_coefficients=curve, power_coefficients=curve)
plant = HeatPlant()
plant.load_state_dict({"pump": pump.state_dict()[""]}, strict=False)
plant.heat_exchanger.update_params(
    thermal_conductance=5e5, hot_nominal_pressure_drop=0, cold_nominal_pressure_drop=0, hot_nominal_mass_flow=40, cold_nominal_mass_flow=40
)
assert plant.is_initialized and not pump.has_input_value("frequency")
plant.set_inputs({"pump.frequency": "50 Hz"})
assert plant.pump.has_input_value("frequency")
```

## Calling modules and `Ports`

Keyword, mapping and positional inlet calls are equivalent. Positional streams follow inlet
declaration order; controls and boundaries remain optional call keywords that apply to this call
only. Do not combine an inlet mapping with inlet keywords.

```python
import gemini as gm

stream = gm.Stream(flow="150 m3/h", T="80 C", p="20 bar")
a = pump(suction=stream, frequency="50 Hz")
b = pump({"suction": stream}, frequency="50 Hz")
c = pump(stream, frequency="50 Hz")
assert a.outputs.head == b.outputs.head == c.outputs.head
assert a.outputs.get("head", unit="bar") == a.outputs.head / 1e5
```

`inlets`, `_compute_outputs` outlets, and `result.outlets` are immutable `Ports`. They preserve
declaration order and support both `ports.suction` and `ports["suction"]`. Unknown names report
the module path, valid names and a close-match suggestion. A call returns a `ModuleResult` with
`outputs` (a `Values` mapping whose `get(name, unit=...)` converts from the declared unit),
`outlets`, `inlets`, the resolved `inputs` and the `children` results of the call.

## Call order and hooks

One call performs these steps:

1. validate inlets and resolve controls and boundaries (call keyword, persisted value, default);
2. run forward pre-hooks;
3. run `forward` and validate its fluid outlet dictionary;
4. run `_compute_outputs`;
5. evaluate composite formula outputs and automatic sums in declaration order;
6. run forward hooks;
7. verify every output was assigned and build `ModuleResult`.

Pre-hooks always receive `(module, inlets)` and forward hooks always receive
`(module, inlets, outlets)`:

```python
def clamp(module, inlets):
    module.frequency = min(module.frequency, 45)


def observe(module, inlets, outlets):
    print(module.head, inlets.suction.p, outlets.discharge.p)


pre_handle = pump.register_forward_pre_hook(clamp)
handle = pump.register_forward_hook(observe)
clamped = pump(suction=stream, frequency=50)
assert clamped.inputs["frequency"] == 45 and not pump.has_input_value("frequency")
pre_handle.remove()
handle.remove()
```

Hook return values are ignored. Any non-fixed hook signature fails at registration with a
`ValidationError`. Remove a hook with `handle.remove()`; removing twice does nothing. Assigning a
control inside a hook changes only the running call.

A pre-hook makes its module a graph break, and so does a forward hook that only reads: the tracer
calls such a hook once on traced values to classify it, then the module runs for real, row by row,
hooks included. A forward hook that writes an output is part of the graph. `EventLog` registers no
hook: it reads the results of each tick.

## Per-call values

The values of one call (resolved controls and boundaries, recorded outputs and the results of
child calls) live in one `_Call` record held in a context variable while the call runs. Attribute
access on a module returns parameter values, the control/boundary value of its running call
(even from a descendant's hook), the persisted value or the default, outputs recorded in its
running call, and port declarations otherwise. Child calls made from pre-hooks are recorded on
the module whose call is running. A module keeps no result after the call returns: use the
returned `ModuleResult`.

## Traced calls

While `gemini.graph` traces a module, its `_Call` carries the running `Trace` (`call.trace`) and a
child call made inside it, from `forward` or from a helper method such as the `produce()` of the nodal doublet example,
is recorded in the graph by `Trace.child` instead of evaluated: the child's controls, boundaries
and numeric parameters become graph inputs named `<path below the root>.<name>`, supplied keyword
values win without validation, and the `ModuleResult` of traced values joins the parent's call
records, so `Output.of`, automatic sums, `Output.ratio` and `ModuleResult.leaves()` work
unchanged. `Output.ratio` is `where(bottom == 0, None, top / bottom)` with the division written as
`ops.truediv`, which gives today's `None` on plain floats. A leaf child that is stateful,
has a pre-hook, has a read-only hook or raises `TraceError` becomes one **break node**:
the graph is rolled back to where the child call started and the child runs on the plain path
(`module(**row)`, a stateful one from its initial states, hooks included) once per row while the
graph is evaluated, its outputs and outlet fields being `break_output` nodes. The outlet fluids
come from one probe of `forward` on representative inlets; a row with another fluid fails. A
failed row is NaN and carries an error code that raises the child's own exception. A composite
child that cannot be recorded makes the whole root a graph
break (`graph.breaks` lists the leaf breaks with their reasons).

An output of a list or tuple of traced values (the per-section profiles of the wells) is a vector
output of fixed length: `Graph.output` records each item as `<name>[<index>]`, `graph.vectors`
keeps the length, and `gemini.graph.run` returns one array of shape `(rows, length)`.

A traced call is not validated, so the tracer adds the validation as graph checks. For every
traced call (children included, break nodes excepted) each control, boundary and output with
bounds (`Declaration.limits()`: `ge`/`gt`/`le`/`lt` read once from the quantity metadata and the
declared bounds, applied to each item of a list; an `X | None` kind lets NaN pass) gets an
`ops.check` raising `ValidationError`, and the root inlets carry the `Stream` limits (finite
`m_dot`, `T > 0`, `p >= 0`). These checks are attached to every graph output, so a row that
violates a bound fails even where the arithmetic never reads the bad value.

## Skipping outputs

`gm.no_outputs()` is a nestable, context-local context manager and decorator. It skips
`_compute_outputs`, formulas, forward hooks and output completeness checks. Fluid forwarding,
pre-hooks and outlet validation still run; the result has an empty `outputs` mapping.

```python
with gm.no_outputs():
    fast = pump(suction=stream, frequency="50 Hz")

assert dict(fast.outputs) == {}
assert fast.outlets.discharge == a.outlets.discharge
```

## State and health

Stateful equipment declares its carried values as `State(kind, default=...)` in the `# States`
section; `default` is the initial state. `forward` and `_compute_outputs` read a state as a plain
attribute (`self.temperature`), which gives its value at the start of the step. A stateful leaf
implements `_advance_states(self, inlets, outlets, dt)`, returning the end-of-step value of every
state, after `_compute_outputs`; a state is never assigned directly. `module.stateful` is true
when a module declares states, and `states(recurse=True)` lists them by dotted path.

`step(state, dt, inlets)` returns `(next_state, result)` for any module. `initial_state()` and
`state` are the module's own `{name: value}` mapping for a leaf and nest by child name for a
composite, for example `{"storage": {"temperature": 330.0}}`; `None` means the initial states.
A composite needs no `step` method: its `forward` runs once, every stateful descendant it calls
starts from its entry and records its end-of-step entry, and a descendant that is not called
keeps its state. A stateful module called twice in one step raises `ValidationError`. Outside
`step`, a call evaluates at the initial states. The engine integrates these steps; see
[engine.md](engine.md). A module that sets `stateful = True` without declaring states must
override `step` itself, and a composite refuses to step such a descendant. The shipped stateful
leaves (`ThermalDecline`, `AquiferStorage`, `BoreholeField`, `ThermalStorage`, `IceStorage`,
`PIDController`) and how each integrates over `dt` are described in
[equipment.md](equipment.md).

```python
from gemini.physics import heat_transfer
from gemini.types import Power, State, Temperature


class Tank(Module):
    """Mixed tank whose temperature follows the inlet."""

    def __init__(self):
        super().__init__()

        # Parameters
        self.heat_capacity = Parameter(float, gt=0)

        # Inlets
        self.inlet = Inlet(Stream)

        # States
        self.temperature = State(Temperature, default=300)

        # Outputs
        self.duty = Output(Power)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Leave at the tank temperature of the start of the step."""

        # Outlets
        outlet = inlets.inlet.with_(T=self.temperature)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.duty = self._duty(inlets.inlet)

    def _advance_states(self, inlets, outlets, dt):
        heat = heat_transfer.heat_rate(self._duty(inlets.inlet), dt)
        rise = heat_transfer.temperature_change(heat, self.heat_capacity)
        return {"temperature": self.temperature + rise}

    def _duty(self, inlet):
        return heat_transfer.heat_rate(inlet.heat_capacity_rate(), inlet.T - self.temperature)


tank = Tank().update_params(heat_capacity=4.2e5)
state, result = tank.step(None, 60, {"inlet": stream})
assert result.outlets.outlet.T == 300 and state["temperature"] > 300
```

A module with a diagnostic model overrides `health(self, result, measured)`. It receives the
call's `ModuleResult` and the measured outputs of that tick and returns a `Health` (`assessed`,
`score`, `alarm`, `message`, `metrics`); the base method returns `None`, which the engine records
as `assessed=False`. A module that declares its own cost defines `capex()` returning a `Cost`;
see [types.md](types.md#profiles-and-costs).

## Structure

Constructor sections are ordered `Modules`, `Parameters`, `Inlets`, `Controls`, `Boundaries`,
`States`, `Outputs`, `Outlets`, with empty sections omitted. `forward` uses only `# Modules` on
composites and `# Outlets` when outlets exist. It contains no `self.<name> = ...` assignments and
ends with `outlets = dict(...)` followed by `return outlets`. Method order is `__init__`,
`forward`, `_compute_outputs`, `_advance_states` when the module has states, then private
helpers. Signatures are always
`forward(self, inlets)` and `_compute_outputs(self, inlets, outlets)`, including modules with no
ports; parameters have no defaults or variadic forms.

Inlets and outlets accept `Stream` types only. Electricity, fuel use and heat exchanged with the
environment or a consumer are additive outputs with the fixed names and quantities of
[types.md](types.md#energy-outputs-and-balances). Results keep the same dotted
`<module path>.<name>` addressing scheme. Port, control and output names follow the naming rule
in [conventions.md](conventions.md#naming).
