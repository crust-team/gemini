# Numerical decisions and known limitations

These decisions preserve the useful evidence from the previous package migration. All original
25 physics cases and eight captured monitoring outputs remain unchanged. Historical graph behaviour
and threshold exceptions are annotated `NOTE(refactor)` next to the implementation or test.

## Retained decisions

- ESP monitoring originally used float32 arithmetic; the public default remains float64, with
  explicit float32 selection in golden reconstruction. Efficiency is a fraction, formerly percent.
- ESP correction factors apply to inferred VLP discharge, not polynomial head. The old affine
  correction fitter and the six-coefficient polynomial fitter are distinct APIs. Plotting scales
  flow by frequency; the forward polynomial retains the original raw-flow basis.
- Historical IPR treated a value labelled m3/h/bar as m3/s/bar. Historical ESP intake omitted
  the trajectory interval crossing pump depth, and inferred discharge used a single vertical
  tubing section. These errors are reproduced only in golden tests. New graphs retain the
  complete trajectory and correct SI productivity. The old first-snapshot correction policy
  has no production caller; configuration selects the date-active snapshot.
- Injection DPDT and corrosion use negative internal flow. Outlet ports now preserve the
  incoming mass-flow sign; numerical pressure/temperature and golden results are unchanged.
- An unconfigured zero aquifer drainage radius yields unavailable radial diagnostics (`None`),
  not infinity. Pressure-flow calculations remain available. The path marcher retains its
  0.001 Pa floor and the original radial-pressure sign convention.
- NORSOK retains exact-temperature pH branches and fallback 7. Erosion retains total fluid
  flow as particle flow, the OKA diameter ambiguity and the unreachable titanium branch.
- Trajectory roughness 2e-5 is metres. DPDT zero-flow behaviour suppresses gravity as well as
  friction, and its gas-velocity expression remains `gmf/rho_g/area`.
- The degasser heat-transfer coefficient has no established physical meaning and is retained
  only as metadata. The source HX value 100,000 is a provisional conductance, not a measured
  calibration. Default missing nominal hydraulic losses remain zero.
- Historical HX tests used 1050 kg/m3 with cp=4217.4. The full example now declares bulk heat
  capacity 4.410 MJ/m3/K with its supplied density 1068 kg/m3, consistent with the CSV heat
  balance. This is an explicit dataset assumption, not independent composition measurement.
- Stream copies revalidate physical constraints. Default fluid properties remain unchanged;
  immutable Fluid overrides travel with every stream. Shared integrity formulas preserve signed
  wall loss, special-value handling and original API velocity conventions.

## New model and configuration decisions

- Filter clean loss is 0.016 bar at 149 m3/h, scaling quadratically with mass flow. Solids loading and
  particle capture are not modelled; the existing clogging diagnostic remains available.
- The degasser passes liquid at configured outlet pressure or inlet minus 0.149 bar, with
  zero gas flow. Booster and blowdown pass streams through and report `modelled=False`.
- No injection-pump curves exist in the project. Use the measured discharge setpoint in twins;
  Q*deltaP/PowerDraw implies efficiency 0.80000 within CSV rounding. The example explicitly
  selects 0.8 while standalone equipment defaults to 0.7. Scenarios default to 51.5 bar.
- The buried ESP is represented by below-pump and riser well segments. The earlier graph used original file stems and an extra `<well>_riser` child;
  the types phase maps these into `doublet.well` and `doublet.riser`. The riser is connected after ESP discharge.
  Both segments use the same trajectory slicing as `intake_conditions` and
  `wellhead_from_discharge`. Segment outputs retain the well schema's `wellhead` field name;
  on the below-pump node this denotes its local upper endpoint (pump intake).
- Port mapping is explicit, including HX primary/secondary ports and both degasser outlets.
  Every unknown property/tag is reported. Empty tags, redundant observations and absent
  measured sandface conditions have individually recorded reasons in `PlantConfig.ignored`.
- Supplemental CSV bindings supply filter pressure differences, HX duty/loss, degasser inlet
  temperature and production rate. Unmeasured secondary pressure is assumed 5 bar absolute.
- Immutable Fluid definitions and import diagnostics live in portable configuration. Each timestep selects
  dated design snapshots; explicitly applied fits persist as overrides until changed.
- Calibration uses dimensionless residuals scaled by each measured output's median magnitude.
  It never applies results unless `apply=True` and the optimizer succeeds. A fit window must
  stay within one dated design snapshot. Vector coefficients use scaled optimizer coordinates.
- Missing data is counted per module/column and skips only that measured twin. Lack of a health
  model is reported as `assessed=False`, never as evidence of healthy operation.

## Measured reconciliation and explicit exceptions

The full CSV has 17,280 rows, all labelled Normal. All eight bound models cover every row.
The two unbound original assets (production well and receiving aquifer) and generated riser
run in chained scenarios, which cover all eleven graph children.

- ESP head median error: **63.1678%**, versus requested 10%. The supplied 15-stage curve
  disagrees with the CSV despite verified SI flow/pressure conversions. The regression limit
  is 65%; no curve was silently fitted to the evaluation period.
- ESP power error: **100%**, because every supplied power coefficient is zero. The regression
  explicitly preserves that limitation. ESP alarm rate is consequently **100%**, versus 5%.
- Filter A/B pressure-loss median errors: **1.6961%**, within the requested 20%.
- Injection-pump power median error: **0.001232%** with the explicit 0.8 efficiency.
- First-week HX fit: UA **7,138,598.617 W/K**; normalised RMS **0.380432 → 0.000294183**.
  Holdout duty median/max errors: **0.6293% / 0.9523%**. Hot outlet median/max absolute
  errors: **0.3388 / 0.5661 K**; cold: **0.3037 / 0.4889 K**. Only the hot maximum limit
  changes, from 0.5 to 0.6 K: apparent UA varies from 3.45 to 10.60 MW/K despite Normal labels.
- Full-chain wellhead-pressure median error: **57.5905%**. The requested 10% is relaxed to
  60% while preserving full geometry, correct productivity and supplied pressure/ESP data.
- Full-chain HX duty median error: **12.4370%**. The requested 10% becomes 15% because the
  supplied reservoir temperature equals measured surface temperature (80 C), while the
  retained nonzero heat-loss model cools the produced stream by about 7 K.
- Raw HX/filter alarm rates are zero. After calibration, held-out HX alarms occur on
  **83.2430%** of rows: declining apparent UA exceeds the existing 15% fouling threshold.
  Keep this diagnostic and report the disagreement with labels; do not suppress it to hit 5%.

The architecture and execution checks pass; these exceptions mean the original physical
accuracy and alarm-rate targets are not all met by the supplied project. Correct pump curves,
reservoir pressure/temperature and an appropriate variable-UA reference are the next data work.


## Types phase: new decisions and limits

- The workspace dataset is still `geothermal_doublet`; no source CSV or golden JSON changed.
  Work is local on `refactor/types`; no push/PR. `core/base` is removed, and `core/types` is
  the public data-type package. GraphPlant, Link and serialized `links` are removed.
- Every numeric equipment contract uses quantity metadata. Polynomial coefficients (ESP and
  injection-pump head/power) remain mixed-unit lists; the unused degasser coefficient remains
  unknown-unit metadata. PipeSection's physics-layer fields declare equivalent metadata
  without an upward import. Empirical ESP efficiency stays unbounded Dimensionless to retain
  original results. ParamRef bounds carry the owner's dynamic unit, not a false common unit.
- `NOTE(refactor)`: well corrosion/erosion helpers retain **mm/year** as the explicit literature
  unit exception. No physics correlation or golden result changed.
- `NOTE(refactor)`: GLYCOL_30 uses inhibited DOWFROST HD reference properties at 40 C and 30%
  propylene glycol by volume: rho=1029.85, cp=3841, k=0.4622, mu=0.0016295 in SI. See the
  manufacturer citation in [types.md](types.md). It is not temperature-dependent; unsupported
  concentrations are rejected. Brine/water defaults remain exactly the old ConstantWater values.
- `NOTE(refactor)`: optional Fluid-based corrosion converts dissolved mass fraction through
  molar mass 0.04401 kg/mol and the existing Henry law at inlet temperature. Salt concentration
  is rho*salinity in kg/m3. This is an inlet/dilute approximation, without salting-out; explicit
  measured gas chemistry retains its previous behavior. Zero specified dissolved CO2 returns
  zero CO2-corrosion contribution when no gas chemistry is supplied.
- `NOTE(refactor)`: ESP electricity is predicted shaft power divided by motor efficiency;
  efficiency defaults to one, preserving every existing power number. Boiler declares both
  fuel and electricity ports, with zero on the unused side, and reports conversion heat loss.
- Wells report signed environmental heat using external mass-flow sign and actual inlet/outlet
  temperatures. Injection's internal negative DPDT flow does not reverse its external balance.
  Stream dtype properties govern stream transport; the golden reconstruction now explicitly
  attaches its original brine to formerly default-water inlet streams. Expected fixtures are
  unchanged. Source composition/property overrides are serialized, with no mutable string registry.
- `NOTE(refactor)`: the physical above-ESP riser remains an explicit child. Diagram verification
  expands ESP->surface into ESP->riser->surface and checks both edges; no connection is ignored.
  The result is ten observed connections and zero missing/extra links.
- Doublet exposes separate production/injection limb methods because surface equipment connects
  the limbs in the parent forward pass. Every equipment call still triggers hooks and capture;
  the grouping object's forward hook runs only when Doublet itself is called.
- ModuleResult now retains the actual inlet/control/child tree while preserving two-value
  unpacking. Aggregation counts leaf energy ports once; composite reporting ports do not duplicate
  energy. Internal fluid transfers cancel in plant boundary totals. Reservoir withdrawal and
  deposition are explicit open-system source/sink boundaries.
- `NOTE(refactor)`: **strict energy closure is not achieved**. Legacy pumps change pressure but
  not temperature and do not allocate their electrical input to mechanical energy or losses.
  The audit preserves a nonzero sum(in)-sum(out), with a separate `unresolved_power` diagnostic.
  No heat-loss port or fictitious shaft work is invented to make a test pass. Thermal accounting
  excludes this explicitly unresolved input and excludes pressure/gravity/kinetic energy.
- On 100 evenly spaced rows, mass residual is zero and maximum relative modeled thermal residual
  is 2.363e-16. Strict energy residual is 212451 W median / 230372 W maximum; median/max relative
  residuals are 0.00176456 / 0.00187310 (normalized by boundary sensible-energy throughput).
  Therefore the requested strict relative energy tolerance 1e-6 remains unmet.
- `NOTE(refactor)`: the missing ESP power curve also prevents the new 10% total-electricity target.
  Median relative error is 38.7345% in measured-boundary twins and 29.7986% in the full chain.
  Existing injection-power accuracy, ESP head/power mismatches and all previous HX/chain/health
  reconciliation metrics remain exactly unchanged. These limitations are asserted and reported,
  not represented as passed physical-accuracy targets.
- Profile sum resampling is summation, not energy integration; indices are UTC and previous
  values are held. Scenario profiles must share an index. Cost aggregation rejects mixed
  currency/year values and sums each module's own sourced contribution once.

See [the types report](../../docs/types-refactor-report.md) for paths, metrics and verification.
