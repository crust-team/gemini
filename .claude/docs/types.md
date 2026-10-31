# Data types

Import public types from `gemini.types`; quantity aliases are defined in
`types/quantities.py`. Types depend on the standard library, Pydantic, pandas/NumPy for
profiles, `gemini.physics` for property calculations, `gemini.errors` and `gemini.utils`. They never
import equipment, the engine or plant files. `Stream.__init__` reads the runtime default fluid
through a function-level import of `gemini.backends.runtime` (see
[conventions.md](conventions.md#dependencies)).

| GEMINI | Purpose |
| --- | --- |
| `Stream` | Immutable mass flow, absolute temperature, pressure and fluid |
| `Ports` | Immutable, ordered module inlet or outlet streams |
| `Fluid` | Immutable composition and overrides; `BRINE`, `WATER`, `GLYCOL_30`, `STEAM` |
| `Parameter`, `Control`, ... | Declared values with a physical unit and validation bounds |
| `ModuleResult` | Recorded outputs, outlets and retained evaluation tree of one call |
| `Values` | Read-only recorded outputs with unit conversion |
| `Health` | Diagnostic comparison of a prediction with measurements |
| `Profile` | UTC time series in a declared SI unit |
| `Cost` | Investment and operating cost with currency, price year and source |
| `value`, `series`, `statistics`, `problem`, `check` | The return shapes, one helper each (`shapes.py`) |
| `OutputUnits` | The `units` argument of a public return, used on the way out (`shapes.py`) |
| `Binding`, `ModuleBindings`, `DatedParams` | Data columns of a module and dated parameters |

## Return shapes

`gemini/types/shapes.py` builds the three shapes of every public return, value, problem and check
([api.md](api.md#return-shapes)), and holds their JSON Schemas, which `scripts/write_schemas.py`
writes to `docs/schemas/`. `value(number, unit, reason=None, **details)` gives `{value, unit}`, with
a `reason` when the value is `None`; `series` adds `time` and `statistics` gives `{min, max, mean}`.
`problem` is defined in `gemini.errors`, a leaf package, because `GeminiError.to_dict` returns one,
and this module exports it. `check(name, passed, measured, limit)` takes two values.

`OutputUnits(units)` is the `units` argument of a public return. It checks the map at the start of a
call and has `value`, `series` and `statistics` of its own, which take the quantity of the number and
give the unit actually used.

## Quantities and declarations

Use `Parameter`, `Inlet`, `Control`, `Boundary`, `State`, `Output` and `Outlet` in module
constructors. Output kinds may be quantity aliases or Python types; inlet and outlet kinds must
be `Stream` types. `Parameter(kind, default=, shape=, calibratable=, description=, **bounds)`
holds design data; `Control` and `Boundary` take `kind`, `default`, `description` and bounds;
`State(kind, default=)` declares a stepped value (see [modules.md](modules.md#state-and-health));
`Output(kind, soft_sensor=, description=)`, the formulas `Output.of` and `Output.ratio` and the
automatic sums of additive outputs are described in
[modules.md](modules.md#composite-modules). `UNSET` denotes an uninitialized parameter and stays
the same object under copy, deep copy and pickling. `shape=` checks fixed vectors; bounds can
tighten quantity defaults.

`declaration.validate(value)` converts a unit string or `gm.Quantity(value, unit)` to the declared
SI unit and then validates it with a Pydantic `TypeAdapter`; a failure raises
`gm.errors.ValidationError`. Plain numbers are taken as SI. A cheap check built once per
declaration is tried first and accepts only the common case, returned unchanged: an exact `float`
inside its bounds (NaN never is), an exact `bool` or `str` for those kinds, `None` for an optional
kind. Everything else, and every failure, takes the full path, so accepted values, coercions and
messages are those of the full path by construction. `declaration.default_value()` validates the
default once and hands out a fresh copy of mutable values. Each declaration exposes `schema`
(the Pydantic JSON schema of its kind), `quantity` and `unit`, read from the annotation; an
optional kind describes its non-null variant and a list describes its items.

Use `Annotated[float, quantity(...)]` aliases for physical numeric declarations, including list
items. `quantity(name, unit, additive=True)` marks a quantity that composites sum over their
descendant leaf calls; the additive quantities are `MassFlow`, the seven energy outputs below,
`Duty` (a heat-transfer rate such as a heat exchanger's) and `HydraulicPower`, all in W except
mass flow, and each has its own quantity name. Plain `Power` is not additive. A declaration's
`additive` attribute reads the flag. Integer stage counts use `Count`. Every quantity's unit is its own SI unit in the unit
table of `physics/units.py` (`test_every_quantity_unit_is_a_known_si_unit`); add the unit
there together with a new quantity. Use signed pressure/temperature *differences* separately
from nonnegative absolute pressure and strictly positive absolute temperature. A difference
converts by scale only: `"5 degC"` as a `TemperatureDifference` is 5 K, not 278.15 K.
Efficiencies used as design constraints are in (0, 1]; empirical ESP output efficiency remains
`Dimensionless` because the unchanged polynomial model can return values above one.

The equipment catalogue ([equipment.md](equipment.md)) added these quantities and units:

| Quantity | SI unit, bounds | Other units | Used by |
| --- | --- | --- | --- |
| `Elevation` | `m`, signed (positive upwards) | `ft` | `Pipe.elevation_change` |
| `MassConcentration` | `kg/m3`, >= 0 | `g/m3`, `mg/l` | `Desander.sand_concentration` |
| `MoneyRate` | `currency/s` | `currency/h` | `GridConnection.cost_rate` |
| `LinearThermalResistance` | `m.K/W`, > 0 | | borehole resistances |
| `TemperatureGradient` | `K/m`, signed | `K/km` | `DownholeHeatExchanger` |

Earlier catalogue work added `Speed` (`m/s`), `Mass` (`kg`, `t`), `SpecificEnthalpy` (`J/kg`,
`kJ/kg`), `HeatCapacity` (`J/K`, `kWh/K`), `VolumetricHeatCapacity` (`J/m3/K`, `MJ/m3/K`),
`ThermalDiffusivity` (`m2/s`), `LinearPower` (`W/m`) and `FlowCoefficient` (`m3/s/Pa^0.5`,
catalogue Kv as `m3/h/bar^0.5`; `ge=0` so a closed valve reports zero, `Valve.flow_coefficient`
keeps `gt=0`). The dimensionless unit `ppm` (1e-6) converts any `-` quantity, for example
`InhibitorDosing.dose = "10 ppm"`. `Duration` accepts `s`, `min`, `h` and `d` (for example
`integral_time="15 min"`), and `ProductivityIndex` accepts `m3/h/bar`.

Add a quantity only when a real field needs a new dimension. Keep local descriptions and
stricter design limits on fields. `tests/unit/modules/test_field_types.py` checks that every
numeric declaration whose kind is not plain `float` or `int` carries a unit, and that
constructor sections are ordered. ESP and injection-pump head/power polynomial coefficients are
plain `list[float]` because their order-dependent legacy US units differ per item; the degasser
coefficient has no established dimension. Physics `PipeSection` keeps plain numeric
annotations to avoid importing types upward, but its four fields carry the same quantity/unit
JSON schema metadata. `Health.metrics` is a heterogeneous diagnostic map, not a single physical
quantity. Calibration accepts the `Parameter` object directly, so no separate parameter
reference type exists. Corrosion/erosion diagnostic helpers retain **mm/year** as an explicit
literature-unit exception; `CorrosionRate` is available for new SI contracts, and conversion
helpers remain in `physics.units`.

## Fluid

`Stream(flow=..., T=..., p=..., fluid=None)` accepts mass flow (`kg/s`, `t/h`) or volumetric flow
(`m3/s`, `m3/h`, `l/s`) and converts it with the stream's fluid density. Plain `flow` numbers are
kg/s; text without a unit such as `flow="150"` raises `gm.errors.ValidationError`, and passing both
`flow` and `m_dot` raises `gm.errors.ValidationError`, as do an unknown keyword (with a did-you-mean),
a missing field and a `fluid` that is neither a `Fluid` nor a mapping of its fields. The explicit
SI `m_dot` field remains supported. Without `fluid` the constructor uses the runtime default
fluid. All public numeric declarations accept a unit string or `gm.Quantity(value, unit)`.
`gm.units.convert(value, from_unit, to_unit, quantity=None)` handles explicit output conversion.

`gm.units` is the one unit implementation (`physics/units.py`, one table). Its public names:
`names(quantity=None)` lists every unit, or those of a named quantity such as `"pressure"`;
`parse("150 m3/h")` returns `(150.0, "m3/h")` (a number, a space and a known unit, else
`ValidationError`); `convert(value, from_unit, to_unit, quantity=None)`; and `fits(unit, quantity)` tells
whether a unit converts to the quantity's SI unit, which is how bindings and CSV headers
`name [unit]` are checked. An unknown unit does not fit and an unknown quantity raises
`ValidationError` with suggestions. The table includes `km`, `mm`, `in`, `kPa`, `MPa`, `rpm`
(1/60 Hz, since frequency is stored in Hz), `degC`, `m3/h`, `kW`, `MW` and `bar(g)`, the same
gauge entry as `barg` (offset 101325 Pa). The SI unit of each quantity name comes from
`quantity(name, unit)` in `types/quantities.py`, which calls `units.define_quantity` once per
quantity, so physics needs no upward import and the quantity list has one source.

`Stream` is one frozen slots dataclass (`m_dot`, `T`, `p`, `fluid`) for every path: plain calls,
batched runs and traces. It has dataclass equality, hash, `repr`, pickling and `copy`; its JSON
(`pydantic_core.to_jsonable_python`) lists `m_dot`, `T`, `p` and `fluid`, and `Stream(**data)`
builds it back. The constructor validates at the boundary: numbers become Python `float`,
`m_dot` must be finite, `T > 0` and finite, `p >= 0` and finite, else `PhysicsError`. When a
field is an array over time or a traced value it is kept as given and the limits become
`gemini.ops.check` calls, so an invalid row raises the same class. `stream.with_(**changes)` is
a trusted fast copy: it reuses the `Fluid`, checks only the changed fields against the same
limits and raises `ValidationError` for an unknown field. A traced inlet is a `Stream` of graph
inputs with the concrete `Fluid`, so `volumetric_flow()` divides by a plain float density.
`Ports` accept only `Stream`. Ports have no JSON schema, quantity or unit in `Declaration`.

`Parameter(..., structural=True)` marks a parameter that decides the shape of the computation (a
loop count, a value that changes a `Fluid`): a trace reads it as a plain value and its value is a
guard of the graph cache; numeric parameters are graph inputs by default.

`BRINE` and `WATER` use the defaults of `gemini.physics.fluid.FluidProperties` (a frozen slots
dataclass: numbers become `float`, bounds raise `PhysicsError`), the original
constant-water numbers. `Fluid` carries salinity, dissolved CO2 and free-gas mass fractions.
`density`, `viscosity`, `specific_heat` and `thermal_conductivity` are validated and immutable, take
unit strings (`"0.4 mPa*s"`) and describe the liquid of a brine or water fluid and the gas of a gas
fluid; a mixture density is a computed property, never an input. Reservoirs hold no density or
viscosity: the fluid owns its properties. A value that does not fit raises `ValidationError`.

Free gas is `gas_liquid_ratio` (normal m3 of free gas per m3 of produced liquid, at 0 degC and
1.01325 bar a, unit `Nm3/m3`) with `gas_composition` (mole fractions summing to one; species `CH4`,
`C2H6`, `C3H8`, `CO2`, `N2`), which derive `gas_mass_fraction` through `physics/gas.py`, or
`gas_mass_fraction` directly; giving both raises `ValidationError`. A dump leaves the derived
fraction out, so it reads back.

`co2_mass_fraction` is the CO2 dissolved in the liquid, which corrosion reads. It is a different
thing from the CO2 in the free gas, which is part of `gas_composition` and which burners carry
through to `co2_emission`.

`Fluid(kind="gas", gas_composition=...)` is a gas fluid, what the `gas` outlet of a `Degasser`
carries. `fluid.density_at(p, T)` is its ideal-gas density at a stream's `p` and `T`, floats, arrays
or traced values, and `stream.volumetric_flow()` uses it; its `properties` snapshot holds the
density at normal conditions.
`fluid.properties(p, T)` returns a `FluidProperties` snapshot cached by the complete Fluid value.
No string registry, registration side effects or string compatibility adapters remain. Salt
concentration alone does not change properties under `constant_stp`; supply measured property
overrides. Gas mass fraction affects homogeneous mixture density.

`GLYCOL_30` denotes 30% propylene glycol **by volume**. Its constant reference values are
1029.85 kg/m3, 3841 J/kg/K, 0.4622 W/m/K and 0.0016295 Pa.s at 40 °C, from the manufacturer's
DOWFROST HD data sheet, page 3:
<https://www.dow.com/content/dam/dcc/documents/en-us/productdatasheet/180/180-01315-01-dowfrost-hd-tds.pdf>.
They represent an inhibited commercial fluid, not a general glycol correlation. Other glycol
fractions are rejected until a suitable model exists. Default water/brine numbers are unchanged.

`Fluid(kind="steam")`, exported as `STEAM`, labels water vapour such as the `gas` outlet of a
flash `Separator`; `FlashTurbine` requires it. Its constant property snapshot is the unchanged
liquid-water default and does not describe vapour: steam equipment takes enthalpies and
entropies from `gemini.physics.steam`, so do not convert a steam stream's volume flow or audit its
latent heat with `cp_l * T`.

Well corrosion helpers accept omitted chemistry: Fluid salt fraction becomes salt concentration
in kg/m3; dissolved CO2 becomes mol/m3 using 0.04401 kg/mol, then partial pressure through the
existing Henry law at inlet temperature. This dilute, constant-inlet approximation does not
include salting-out. Explicit measured gas chemistry remains supported and takes precedence.
Zero dissolved CO2 with no supplied gas chemistry returns zero CO2-corrosion rates; it does not
claim absence of other corrosion mechanisms.

## Energy outputs and balances

Energy that crosses a leaf other than in its streams is reported as outputs with fixed names,
each declared with its own additive quantity in W (`Electricity`, `Fuel`, `HeatAbsorbed`,
`HeatLoss`, `HeatSupplied`, `ElectricityGenerated`, `HeatAccumulation`); they are not flow
ports. Six are nonnegative: the inflows `electricity` and `fuel` consumed
and `heat_absorbed` from outside the plant (ambient air, the ground, a cooled building), and the
outflows `heat_loss` to the environment, `heat_supplied` to a consumer and `electricity_generated`.
`ENERGY_INPUTS` and `ENERGY_OUTPUTS` in `modules/balance.py` list them. The seventh,
`heat_accumulation`, is signed: the rate of increase of the heat a storage leaf holds
(`ThermalStorage`, `IceStorage`, `AquiferStorage`), counted with the outflows, so a charging store
(positive) and a discharging one (negative) both close. Declare only the outputs a module has. Fluid
heat transferred between equipment remains in `Stream` states. `collect_flows(result)` sums these
leaf outputs once, ignoring composite aggregates. `ModuleResult` captures incoming streams, controls
and children at evaluation time; later evaluations do not replace these audit inputs.

`mass_balance(module, result)` includes aquifer withdrawal/deposition boundaries.
`energy_balance(module, result)` audits sensible enthalpy (`m_dot * cp_l * T`) and these seven
energy outputs. Internal stream transfers cancel once; reported plant totals are boundary
fluxes. Pressure, kinetic and gravitational energy are outside the thermal model.
`residual` is always sum(in) minus sum(out). `thermal_residual` separately excludes
**unresolved pump power**. The legacy isothermal pumps do not allocate electricity to work or
heat; their nonzero strict energy residual must remain visible. A small thermal residual is not
full first-law closure. The audit status of every shipped module, including the documented
residuals of models that are deliberately not closed per call or whose energy is not sensible
liquid enthalpy (gas, steam), is listed in [equipment.md](equipment.md).

`emissions(result, fuel_factor, electricity_factor)` turns the same leaf totals into a rate for any
topology: `fuel * fuel_factor + max(0, electricity - electricity_generated) * electricity_factor`.
Factors are SI kg/J (kg/GJ / 1e9, kg/kWh / 3.6e6; the unit table has no emission-factor units). All
on-site generation offsets the electricity of all consumers (ESP, pumps, compressors, heat pumps), not
only the ESP as in the upstream GEMINI KPI, before grid electricity is charged; a surplus earns no
credit. `gm.economics` uses it for the energies drawn; the CO2 of a run comes from the `co2_emission`
and `methane_emission` outputs, which follow the gas composition.

## Profiles and costs

`Profile.from_series(series, unit, tz="UTC")` converts an in-memory pandas Series in any unit of
the `physics.units` table whose SI unit is W, K, Pa, kg/s, m3/s, Hz, J, currency/J or `-`
(for example degC, bar, kW, MW, kWh, m3/h and currency/kWh). Naive timestamps are interpreted in
`tz`; storage is UTC. `Profile.constant(value, unit=..., clock=...)` builds a constant profile on
every tick of a clock from a raw-unit value. Indices must be nonempty, unique and strictly
increasing, with finite matching values. `at(t)` holds the latest sample at or before `t`; times
before the first sample raise `RunError`. `resample(step, how)` supports mean/sum/first and
rejects empty bins with `RunError`. Sum is a sum of sample values, not time integration.

Simulate profiles by combining them into a dataset keyed by dotted control or boundary paths:
`gm.simulate(plant, gm.Dataset.from_profiles(profiles), clock)`. Profiles combined into a
dataset must share one index; resample explicitly.

`Cost` stores investment, annual fixed cost and variable currency/J of useful output, together
with currency, price year and a source citation. A module declares its own cost by defining
`capex(assumptions)` returning a `Cost`; `gemini.types.cost.total_cost(plant, assumptions)` sums each
module's own contribution once, returns `None` when no module declares a cost and rejects mixed
currencies or years. Composite `capex` must therefore describe only its own additional cost, not
repeat child costs. `scaled_cost(assumptions, factor, size)` is a factor times a design size.
