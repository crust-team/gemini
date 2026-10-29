# Core data types

Import public types from `gemini.core.types`; quantity aliases are defined in
`core/types/quantities.py`. Types depend on the standard library, Pydantic, pandas/NumPy for
profiles, `core.physics` for property calculations, `gemini.errors` and `gemini.utils`. They never
import equipment, the engine or plant files. `Stream.__init__` reads the runtime default fluid
through a function-level import of `core.runtime` (see
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
| `Binding`, `ModuleBindings`, `DatedParams` | Data columns of a module and dated parameters |

## Quantities and declarations

Use `Parameter`, `Inlet`, `Control`, `Boundary`, `State`, `Output` and `Outlet` in module
constructors. Output kinds may be quantity aliases or Python types; inlet and outlet kinds must
be `Stream` types. `Parameter(kind, default=, shape=, calibratable=, description=, **bounds)`
holds design data; `Control` and `Boundary` take `kind`, `default`, `description` and bounds;
`State(kind, default=)` declares a stepped value (see [modules.md](modules.md#state-and-health));
`Output(kind, soft_sensor=, description=)` and the formulas `Output.of`, `Output.total` and
`Output.ratio` are described in [modules.md](modules.md#composite-modules). `UNSET` denotes an
uninitialized parameter and stays the same object under copy, deep copy and pickling. `shape=`
checks fixed vectors; bounds can tighten quantity defaults.

`declaration.validate(value)` converts a unit string or `gm.Quantity(value, unit)` to the declared
SI unit and then validates it with a Pydantic `TypeAdapter`; a failure raises
`gm.errors.DeclarationError`. Plain numbers are taken as SI. Each declaration exposes `schema`
(the Pydantic JSON schema of its kind), `quantity` and `unit`, read from the annotation; an
optional kind describes its non-null variant and a list describes its items.

Use `Annotated[float, quantity(...)]` aliases for physical numeric declarations, including list
items. Integer stage counts use `Count`. Every quantity's unit is its own SI unit in the unit
table of `core/physics/units.py` (`test_every_quantity_unit_is_a_known_si_unit`); add the unit
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
stricter design limits on fields. `tests/unit/core/modules/test_field_types.py` checks that every
numeric declaration whose kind is not plain `float` or `int` carries a unit, and that
constructor sections are ordered. ESP and injection-pump head/power polynomial coefficients are
plain `list[float]` because their order-dependent legacy US units differ per item; the degasser
coefficient has no established dimension. Core physics `PipeSection` keeps plain numeric
annotations to avoid importing types upward, but its four fields carry the same quantity/unit
JSON schema metadata. `Health.metrics` is a heterogeneous diagnostic map, not a single physical
quantity. Calibration accepts the `Parameter` object directly, so no separate parameter
reference type exists. Corrosion/erosion diagnostic helpers retain **mm/year** as an explicit
literature-unit exception; `CorrosionRate` is available for new SI contracts, and conversion
helpers remain in `physics.units`.

## Fluid

`Stream(flow=..., T=..., p=..., fluid=None)` accepts mass flow (`kg/s`, `t/h`) or volumetric flow
(`m3/s`, `m3/h`, `l/s`) and converts it with the stream's fluid density. Plain `flow` numbers are
kg/s; text without a unit such as `flow="150"` raises `gm.errors.UnitError`, and passing both
`flow` and `m_dot` raises `TypeError`. The explicit SI `m_dot` field remains supported. Without
`fluid` the constructor uses the runtime default fluid, while `Stream.model_validate` uses the
field default `BRINE`. `stream.with_(**changes)` returns a validated copy. All public numeric
declarations accept a unit string or `gm.Quantity(value, unit)`. `gm.units.convert(value,
from_unit, to_unit, quantity=None)` handles explicit output conversion.

`BRINE` and `WATER` use the defaults of `core.physics.fluid.FluidProperties`, the original
constant-water numbers. `Fluid` carries salinity, dissolved CO2 and free-gas mass fractions.
Density, viscosity, heat capacity and conductivity overrides are validated and immutable.
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
entropies from `core.physics.steam`, so do not convert a steam stream's volume flow or audit its
latent heat with `cp_l * T`.

Well corrosion helpers accept omitted chemistry: Fluid salt fraction becomes salt concentration
in kg/m3; dissolved CO2 becomes mol/m3 using 0.04401 kg/mol, then partial pressure through the
existing Henry law at inlet temperature. This dilute, constant-inlet approximation does not
include salting-out. Explicit measured gas chemistry remains supported and takes precedence.
Zero dissolved CO2 with no supplied gas chemistry returns zero CO2-corrosion rates; it does not
claim absence of other corrosion mechanisms.

## Energy outputs and balances

Energy that crosses a leaf other than in its streams is reported as `Power` outputs with fixed
names; they are not flow ports. Six are nonnegative: the inflows `electricity` and `fuel` consumed
and `heat_absorbed` from outside the plant (ambient air, the ground, a cooled building), and the
outflows `heat_loss` to the environment, `heat_supplied` to a consumer and `electricity_generated`.
`ENERGY_INPUTS` and `ENERGY_OUTPUTS` in `core/modules/balance.py` list them. The seventh,
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

## Profiles and costs

`Profile.from_series(series, unit, tz="UTC")` converts an in-memory pandas Series in any unit of
the `physics.units` table whose SI unit is W, K, Pa, kg/s, m3/s, Hz, J, currency/J or `-`
(for example degC, bar, kW, MW, kWh, m3/h and currency/kWh). Naive timestamps are interpreted in
`tz`; storage is UTC. `Profile.constant(value, unit=..., clock=...)` builds a constant profile on
every tick of a clock from a raw-unit value. Indices must be nonempty, unique and strictly
increasing, with finite matching values. `at(t)` holds the latest sample at or before `t`; times
before the first sample raise `DatasetError`. `resample(step, how)` supports mean/sum/first and
rejects empty bins with `DatasetError`. Sum is a sum of sample values, not time integration.

Simulate profiles by combining them into a dataset keyed by dotted control or boundary paths:
`gm.Engine().simulate(plant, gm.Dataset.from_profiles(profiles), clock)`. Profiles combined into a
dataset must share one index; resample explicitly.

`Cost` stores investment, annual fixed cost and variable currency/J of useful output, together
with currency, price year and a source citation. A module declares its own cost by defining
`capex()` returning a `Cost`; `gemini.core.types.cost.total_cost(plant)` sums each module's own
contribution once, returns `None` when no module declares a cost and rejects mixed currencies or
years. Composite `capex` must therefore describe only its own additional cost, not repeat child
costs. No built-in module declares a cost.
