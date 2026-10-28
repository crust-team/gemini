# Types and handwritten-plant refactor report

Implemented locally on `refactor/types`, based on `4249f10`. No push or PR. The dataset remains
`datasets/geothermal_doublet`, matching the workspace rather than the attachment's older name.
Source CSV/.param data and both immutable golden JSON fixtures are unchanged.

The software architecture, golden preservation, wiring, mass and modeled thermal checks pass.
**The requested strict energy closure and <10% total electricity error are not achieved.**
The preserved isothermal pumps have no thermodynamic allocation for electrical work, and the
supplied ESP power coefficients are all zero. The implementation exposes these failures rather
than inventing loss/work or suppressing a residual.

## Final trees

Core, two levels (equipment/plant files are inside the shown category directories):

```text
gemini/core/
├── config/
│   ├── __init__.py
│   ├── build.py
│   ├── gemini_loader.py
│   ├── param_mapping.py
│   ├── schema.py
│   └── wiring.py
├── data/
│   ├── connector/
│   ├── __init__.py
│   ├── csv_memory.py
│   ├── database_driver_abstract.py
│   ├── database_reader_abstract.py
│   ├── influxdb_aveva_reader_db.py
│   ├── influxdb_csv_reader_db.py
│   └── timeseries.py
├── engine/
│   ├── __init__.py
│   ├── events.py
│   ├── registry.py
│   └── results.py
├── modes/
│   ├── __init__.py
│   ├── history.py
│   ├── live.py
│   ├── scenario.py
│   └── twin.py
├── modules/
│   ├── heat/
│   ├── plants/
│   ├── pumps/
│   ├── subsurface/
│   ├── treatment/
│   ├── __init__.py
│   ├── balance.py
│   └── module.py
├── physics/
│   ├── __init__.py
│   ├── chemistry.py
│   ├── constants.py
│   ├── corrosion.py
│   ├── erosion.py
│   ├── fluid.py
│   ├── geometry.py
│   ├── heat_transfer.py
│   ├── hydraulics.py
│   ├── pumps.py
│   └── units.py
├── types/
│   ├── __init__.py
│   ├── cost.py
│   ├── flows.py
│   ├── fluid.py
│   ├── profile.py
│   ├── quantities.py
│   └── results.py
└── __init__.py
```

Tests, three levels (equipment test files are inside the shown category directories):

```text
tests/
├── core/
│   ├── config/
│   │   ├── test_config.py
│   │   └── test_param_mapping.py
│   ├── data/
│   │   ├── credentials/
│   │   ├── __init__.py
│   │   └── test_avevadb_driver.py
│   ├── engine/
│   │   └── test_registry.py
│   ├── modes/
│   │   └── test_modes.py
│   ├── modules/
│   │   ├── heat/
│   │   ├── pumps/
│   │   ├── subsurface/
│   │   ├── treatment/
│   │   ├── test_balance.py
│   │   ├── test_contracts.py
│   │   ├── test_field_types.py
│   │   ├── test_module.py
│   │   └── test_plant.py
│   ├── physics/
│   │   ├── test_chemistry.py
│   │   ├── test_corrosion.py
│   │   ├── test_fluid.py
│   │   ├── test_hydraulics.py
│   │   ├── test_physics.py
│   │   └── test_units.py
│   ├── types/
│   │   ├── __init__.py
│   │   ├── test_cost.py
│   │   ├── test_fluid.py
│   │   ├── test_profile.py
│   │   └── test_quantities.py
│   └── __init__.py
├── e2e/
│   └── test_geothermal_example.py
├── golden/
│   ├── __init__.py
│   ├── capture_golden.py
│   ├── evaluate.py
│   ├── golden_values.json
│   ├── runtime_values.json
│   ├── test_golden.py
│   └── test_runtime.py
├── __init__.py
└── test_examples.py
```

## Paths and API changes

- `git mv core/base` -> `core/types`; `stream.py` -> `flows.py`, `health.py` -> `results.py`.
- Move ModuleResult and ParamRef from `core/modules/module.py` into `core/types/results.py`.
  No removed-name compatibility adapters remain; public types are re-exported from core.types.
- Add quantities.py, fluid.py, profile.py and cost.py; remove the mutable physics string-fluid
  registry. Immutable Fluid values now serialize with streams, configuration and state snapshots.
- Delete `core/modules/plant.py` / GraphPlant and config Link/links.
- Add handwritten `modules/plants/doublet.py`, `geothermal_example.py`, `modules/balance.py`
  and identity-based `config/wiring.py`. Port tuples become name-to-Flow-type mappings.
- Update run modes, registry, configuration and saved plant.json to dotted child paths.
  Add example 10 (57 formatted lines, about 40 nonblank lines) and update all existing callers.
- Add types tests, numeric-schema enforcement and balance/wiring checks; replace graph-tearing
  tests with handwritten-plant tests and retain nested stateful composition coverage.
- Add `.claude/docs/types.md`; update instructions, module/convention/physics/testing guides,
  README, changelog and numerical notes. Old generated API stubs were archived outside the repo
  and regenerated so deleted base/graph modules cannot remain in the documentation build.

## Quantity allow-list and dimensional details

| Contract field | Reason |
| --- | --- |
| ESP.Params.head_coeff | Polynomial orders have different ft/stage vs bbl/day dimensions |
| ESP.Params.power_coeff | Polynomial orders have different bhp/stage vs bbl/day dimensions |
| InjectionPump.Params.head_coeff | Same legacy US-basis polynomial convention |
| InjectionPump.Params.power_coeff | Same legacy US-basis polynomial convention |
| Degasser.Params.heat_transfer_coeff | Unused metadata with undocumented physical meaning |

Every other numeric equipment field has quantity metadata, including typed array items,
integer stage counts and separate slope/pressure units for correction tuples. Recursive schema
tests cover nested Fluid, Stream and PipeSection definitions. Physics PipeSection fields retain
plain annotations with equivalent unit/quantity metadata to preserve dependency direction.
Health.metrics remains a heterogeneous diagnostic dictionary; ParamRef bounds carry their
parameter's quantity and unit. ESP empirical output efficiency stays Dimensionless because
unchanged legacy calculations are not constrained to [0,1]. Corrosion/erosion helper rates retain
**mm/year** as an explicit documented exception; underlying physics functions are unchanged.

## Energy ports and balances

| Module | Reporting outlets beyond fluid ports |
| --- | --- |
| ESP | electricity = predicted shaft power / motor_efficiency; default efficiency 1 |
| InjectionPump | electricity = existing predicted power |
| Boiler | electricity, fuel (unused side zero), heat_loss = energy input minus duty |
| ProductionWell / InjectionWell | signed heat_loss = external m_dot * cp * (Tin - Tout) |
| Doublet / GeothermalExamplePlant | aggregate electricity and heat_loss; counted once via leaves |
| HeatExchanger | none; both thermal sides are fluid streams |
| Filter / Degasser / Blowdown / BoosterPump | none; no modeled electricity or environmental heat |

On **100 evenly spaced rows**, every equipment leaf is checked:

| Audit | Result |
| --- | --- |
| Maximum plant mass relative residual | 0 |
| Maximum modeled thermal relative residual | 2.362806e-16 |
| Strict energy residual, median / max | 212451.165 / 230371.858 W |
| Strict energy relative residual, median / max | 0.00176456 / 0.00187310 |
| Requested strict relative energy tolerance | 1e-6 — **not met** |

Aquifers are open withdrawal/deposition boundaries. Internal stream transfers cancel once.
Sensible enthalpy is m_dot*cp_l*T; pressure, gravity and kinetic energy are outside this retained
thermal model. `residual` includes all reported electricity/fuel and therefore remains nonzero
for isothermal pumps. `unresolved_power` identifies unallocated pump electricity;
`thermal_residual` is separately named and must not be treated as full first-law closure.
Boiler tests demonstrate true modeled first-law closure including conversion losses.

## Before/after reconciliation

Both runs use all 17,280 records, the same 672-row first-week calibration window and 16,608-row
holdout. Existing metrics are numerically identical, not merely within relaxed tolerances.

| Metric | Before | After |
| --- | ---: | ---: |
| Eight measured-twin coverage | 100% | 100% |
| Unknown imported fields | 0 | 0 |
| ESP head median relative error | 63.167759% | 63.167759% |
| ESP power median relative error | 100% | 100% |
| Both filter loss median errors | 1.696102% | 1.696102% |
| Injection-pump power median error | 0.001232% | 0.001232% |
| Fitted HX UA | 7,138,598.616760 W/K | 7,138,598.616760 W/K |
| Calibration normalized RMS | .380431578 -> .000294183 | identical |
| Holdout HX duty median / max error | .629295% / .952329% | identical |
| Holdout hot outlet median / max error | .338790 / .566082 K | identical |
| Holdout cold outlet median / max error | .303712 / .488888 K | identical |
| Chained wellhead median error | 57.590482% | 57.590482% |
| Chained HX duty median error | 12.437011% | 12.437011% |
| ESP alarm rate | 100% | 100% |
| Calibrated holdout HX alarm rate | 83.243015% | 83.243015% |
| Total electricity median error, measured boundaries | not previously reported | 38.734543% |
| Total electricity median error, chained | not previously reported | 29.798559% |

The new electricity targets fail the requested 10% threshold. The current prediction is only
injection-pump power because supplied ESP power coefficients are zero. Existing model/data
exceptions remain explicit. The previous report is `docs/reconciliation.json`; new machine-readable
results, including balances and electricity, are `docs/types-reconciliation.json`.

## Wiring and GEMINI_NODES

Ten observed physical links, **zero missing or extra connections** against all nine original
diagram links after the explicit above-ESP riser expansion. Both expanded edges are checked.
The diagram does not construct the plant.

| Imported .param stem | Handwritten child path |
| --- | --- |
| reservoir_c1b5 | doublet.reservoir |
| production_well_c774 | doublet.well |
| esp_1ee3 | doublet.esp |
| degasser_e846 | degasser |
| filter_b2e6 | filter_hot |
| heat_exchanger_3410 | heat_exchanger |
| filter_b1ed | filter_return |
| injection_pump_3808 | injection_pump |
| injection_well_a06b | doublet.injector |
| reservoir_28fc | doublet.sink |

`doublet.riser` is the explicit generated above-ESP segment, sharing the original well geometry.
Doublet's separate produce/inject limbs let parent forward connect the surface loop in one pass;
all equipment uses normal module calls and therefore leaf hooks. Standalone Doublet.forward
accepts an independently specified return stream.

## New NOTE(refactor) decisions

1. ESP motor efficiency defaults to 1; electricity reports shaft power / efficiency.
2. Boiler declares electricity and fuel statically, with zero for the unused energy source.
3. Wells retain mm/year corrosion/erosion diagnostics as the explicit SI exception.
4. Glycol reference properties are for inhibited DOWFROST HD at 40 C, 30% propylene glycol
   **by volume**: rho=1029.85 kg/m3, cp=3841 J/kg/K, k=.4622 W/m/K, mu=.0016295 Pa.s.
   Source: [manufacturer data sheet, page 3](https://www.dow.com/content/dam/dcc/documents/en-us/productdatasheet/180/180-01315-01-dowfrost-hd-tds.pdf).
5. Fluid-derived corrosion uses dissolved CO2 mass -> moles -> Henry-law partial pressure;
   salinity becomes salt concentration. It is an inlet-temperature, dilute approximation.
   Measured gas chemistry remains an explicit override; zero CO2 gives zero CO2 contribution.
6. Diagram verification explicitly expands the omitted physical riser and verifies both edges.
7. Retain the previous example heat-capacity inference, 4.410 MJ/m3/K, in immutable Fluid.
8. Report unresolved isothermal-pump energy rather than inventing heat or mechanical work;
   strict first-law closure remains unmet despite modeled thermal closure.
9. Record the missing-ESP-curve total-electricity exception rather than forcing the 10% target.

Additional API decisions: state snapshots now include Fluid; ModuleResult retains audit metadata
while supporting two-value unpacking; profiles use UTC previous-sample holds and explicit index
alignment; costs reject mixed currency/year. Public physical quantities are re-exported from
types. No optimizer, new pump curve, network solver or mutable compatibility registry was added.

## Verification

- `pytest tests -q`: **141 passed, 1 skipped in 51.77s**; only AVEVA credentials are absent.
- `black --check gemini tests examples`: **122 files would be left unchanged**.
- `isort --check-only gemini tests examples`: **clean**.
- `flake8 gemini tests examples`: **clean**.
- `sphinx-build -W -E -b html docs /tmp/gemini-types-docs`: **build succeeded**.
- `git diff --check`: **clean**.
- Both golden JSON fixtures: **unchanged**. All ten executable examples pass.

Seven local phase commits, no push and no PR. Passing tests include explicit regression checks
for the known energy/electricity limitations; they do not mean those requested physical targets
were met.
