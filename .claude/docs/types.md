# Core data types

Import public types from `gemini.core.types`; quantity aliases are also defined in
`core/types/quantities.py`. Types depend on stdlib, Pydantic, pandas/NumPy for profiles, and
`core.physics` for property calculations. They never import equipment, registry or configuration.

| PyTorch analogy | GEMINI | Purpose |
| --- | --- | --- |
| Tensor | `Stream` | Immutable mass flow, absolute temperature and pressure |
| Tensor mapping | `Ports` | Immutable, ordered module inlet or outlet streams |
| dtype | `Fluid` | Immutable composition and constant-property overrides |
| Parameter | `Parameter` declaration | Design value with physical unit and validation bounds |
| Forward result | `ModuleResult` | Recorded outputs, outlets and retained evaluation tree |
| Input sequence | `Profile` | UTC time series in declared SI units |

## Quantities and schemas

Use `Parameter`, `Inlet`, `Control`, `Boundary`, `Output` and `Outlet` in module constructors.
Output kinds may be quantity aliases or Python types; inlet and outlet kinds must be `Stream`
types. Pydantic `TypeAdapter` performs
validation after declarations convert unit-bearing public values to SI. `UNSET` denotes an
uninitialized parameter; `shape=` checks fixed vectors; bounds can tighten quantity defaults.

Use `Annotated[float, quantity(...)]` aliases for physical numeric declarations, including list
items. Integer stage counts use `Count`. Use signed pressure/temperature *differences*
separately from nonnegative absolute pressure and strictly positive absolute temperature.
Efficiencies used as design constraints are in (0, 1]; empirical ESP output efficiency remains
`Dimensionless` because the unchanged polynomial model can return values above one.

Add a quantity only when a real field needs a new dimension. Keep local descriptions and
stricter design limits on fields. `Module.schema()` retains Pydantic JSON schema, including
`$defs`, and annotates properties with `name`, `quantity`, `unit`, `bounds`, `description` and
`default`. Required fields remain identified by JSON schema `required`, not by null defaults.
Homogeneous arrays expose their item unit; correction tuples expose each item's unit.

The enforced equipment allow-list is in `tests/core/modules/test_field_types.py`:
ESP and injection-pump head/power polynomial coefficients have order-dependent legacy US units;
the unused degasser coefficient has no established dimension. Core physics `PipeSection`
keeps plain numeric annotations to avoid importing types upward, but its four fields carry
identical quantity/unit JSON metadata, checked recursively by the schema test.
`Health.metrics` is a heterogeneous diagnostic map, not a single physical quantity.
Calibration accepts the registered `Parameter` object directly, so no separate parameter
reference type exists. Corrosion/erosion diagnostic helpers retain
**mm/year** as an explicit literature-unit exception; `CorrosionRate` is available for new SI
contracts, and conversion helpers remain in `physics.units`.

## Fluid

`Stream(flow=..., T=..., p=..., fluid=None)` accepts mass flow (`kg/s`, `t/h`) or volumetric flow
(`m3/s`, `m3/h`, `l/s`) and converts using the selected fluid. Plain `flow` numbers are kg/s;
the explicit SI `m_dot` field remains supported. All public numeric declarations accept a unit
string or `gm.Quantity(value, unit)`. `gm.units.convert` handles explicit output conversion.

`BRINE` and `WATER` retain the original ConstantWater numerical properties. `Fluid` carries
salinity, dissolved CO2 and free-gas mass fractions. Density, viscosity, heat capacity and
conductivity overrides are validated and immutable. Model factories are cached by the complete
Fluid value. No string registry, registration side effects or string compatibility adapters remain.
Salt concentration alone does not change properties under `constant_stp`; supply measured
property overrides. Gas mass fraction affects homogeneous mixture density.

`GLYCOL_30` denotes 30% propylene glycol **by volume**. Its constant reference values are
1029.85 kg/m3, 3841 J/kg/K, 0.4622 W/m/K and 0.0016295 Pa.s at 40 °C, from the manufacturer's
[DOWFROST HD data sheet, page 3](https://www.dow.com/content/dam/dcc/documents/en-us/productdatasheet/180/180-01315-01-dowfrost-hd-tds.pdf).
They represent an inhibited commercial fluid, not a general glycol correlation. Other glycol
fractions are rejected until a suitable model exists. Default water/brine numbers are unchanged.

Well corrosion helpers accept omitted chemistry: Fluid salt fraction becomes salt concentration
in kg/m3; dissolved CO2 becomes mol/m3 using 0.04401 kg/mol, then partial pressure through the
existing Henry law at inlet temperature. This dilute, constant-inlet approximation does not
include salting-out. Explicit measured gas chemistry remains supported and takes precedence.
Zero dissolved CO2 with no supplied gas chemistry returns zero CO2-corrosion rates; it does not
claim absence of other corrosion mechanisms.

## Energy outputs and balances

Electricity, fuel use and environmental heat loss are `Power` outputs named `electricity`,
`fuel` and `heat_loss`; they are not flow ports. Fluid heat transferred between equipment remains
in `Stream` states. `collect_flows(result)` sums these leaf outputs once, ignoring composite
aggregates. `ModuleResult` captures incoming streams, controls and children at evaluation time;
later evaluations do not replace these audit inputs.

`mass_balance` includes aquifer withdrawal/deposition boundaries. `energy_balance` audits
sensible enthalpy (`m_dot * cp_l * T`), electricity, fuel and reported environmental heat.
Internal stream transfers cancel once; reported plant totals are boundary fluxes. Pressure,
kinetic and gravitational energy are outside the thermal model. `residual` is always
sum(in) minus sum(out). `thermal_residual` separately excludes **unresolved pump power**.
The legacy isothermal pumps do not allocate electricity to work or heat; their nonzero strict
energy residual must remain visible. A small thermal residual is not full first-law closure.

## Profiles and costs

`Profile.from_series` converts supported in-memory units with `physics.units.to_si`, including Celsius,
kW/MW, kWh and currency/kWh. Naive timestamps are interpreted in the supplied timezone or UTC;
storage is UTC. Indices must be nonempty, unique and strictly increasing, with finite matching
values. `at(t)` holds the latest sample at or before t; times before the first sample raise.
`resample` supports mean/sum/first and rejects empty bins. Sum is a sum of sample values,
not time integration. `constant` accepts values already in their stated SI unit.

`scenario.run(plant, profiles, dt, base_inputs=...)` maps profile keys to input fields; dotted
keys address nested fields. Profiles must have identical indices; resample explicitly.
For stateful scenarios, dt remains the caller's explicit integration step in seconds.

`Cost` stores investment, annual fixed cost and variable currency/J of useful output, together
with currency, price year and a source citation. `Module.capex()` returns an optional Cost;
`Module.cost()` sums each module's own contribution once and rejects mixed currencies or years.
Composite `capex` must therefore describe only its own additional cost, not repeat child costs.
