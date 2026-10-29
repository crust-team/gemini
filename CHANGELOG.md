# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

The package was rebuilt as composable modules with handwritten plants, in-memory data and one
finite engine, and then cleaned up. Old import paths are not retained.

### Added
- Composable `Module` equipment with declared parameters, ports, controls, boundaries and
  outputs, the handwritten `Doublet` plant and the example `DoubletHeatPlant`, portable plant
  JSON with dated parameters and bindings, and the `gm.legacy` bridge to old GEMINI projects.
- `Engine.simulate`, `Engine.replay` and `Engine.live` with callbacks, results, checkpoints and
  resume; bounded calibration through replay; quantity declarations, immutable fluids, profiles,
  costs and mass/energy audits. Eight runnable examples under `examples/`.
- Leaf packages `gemini.utils` (shared string, time, hook, mapping, context and file helpers;
  `python -m gemini.utils.collect_env`) and `gemini.errors` (every error class, also deriving
  from the matching built-in exception, as `gm.errors`).
- Development and release test profiles: `make test` runs `scripts/test_changed.py` on what
  changed and what imports it within a 300 s budget, `make test-release` runs every tier on the
  full-year data; CI runs the development profile on feature branches and the release profile
  for `main`.
- Quality gates: `tests/unit/test_code_quality.py` (comments, nesting, function length,
  framework name), flake8 `max-complexity = 10` without ignoring bare `except`, the package
  boundary test and mirror tests for every source file.
- Equipment classes in `gm.modules`, each described in `.claude/docs/equipment.md`:
  - pumps `CentrifugalPump`, `LineShaftPump`, `GasCompressor`;
  - piping `Pipe`, `Valve`, `Splitter`, `Mixer`, `PressurizationTank`;
  - treatment `Desander`, `InhibitorDosing`, `Vent`;
  - heat `HeatPump`, `AbsorptionUnit`, `AdsorptionChiller`, `CHP`, `Cooler`;
  - subsurface `ThermalDecline`, `AquiferStorage`, `BoreholeField`, `DownholeHeatExchanger`;
  - storage `ThermalStorage`, `IceStorage`; control `PIDController`;
  - power `ORC`, `Separator`, `FlashTurbine`, `GridConnection`;
  - demand `HeatConsumer`, `CoolingConsumer`.
- Composite plants in `gm.plants`: `MultiWellPlant`, `HeatingSubstation`, `CoolingSubstation`,
  `DistrictNetwork` (heating or cooling) and `ATESPlant`, with the example
  `examples/core/simulate/01_district_heating_and_cooling.py`; `Module.trial_outlets` and
  `Module.start_states` for loops closed within one call.
- Physics modules `compression`, `refrigeration`, `steam` (IAPWS-IF97), `ground` and
  `psychrometrics`.
- `State(kind, default=...)` declarations with `_advance_states(inlets, outlets, dt)`: any module
  steps with `module.step(state, dt, inlets)`, and a composite steps every stateful descendant
  through its own `forward`, without a hand-written step method.
- Energy-balance terms beyond `electricity`, `fuel` and `heat_loss`: `heat_absorbed`,
  `heat_supplied`, `electricity_generated` and the signed stored-heat rate `heat_accumulation`
  (`ENERGY_INPUTS` and `ENERGY_OUTPUTS` in `gemini/core/modules/balance.py`).
- Quantities `Elevation`, `MassConcentration`, `MoneyRate`, `LinearThermalResistance`,
  `TemperatureGradient`, `Speed`, `Mass`, `SpecificEnthalpy`, `HeatCapacity`,
  `VolumetricHeatCapacity`, `ThermalDiffusivity` and `LinearPower`; units `g/m3`, `mg/l`, `ppm`,
  `currency/s`, `currency/h`, `m.K/W`, `K/m`, `K/km`, `kJ/kg`, `kWh/K`, `MJ/m3/K`, `t` and
  `m3/h/bar^0.5`; the `Fluid` kind `"steam"` and the `STEAM` constant.
- `Degasser.separation_efficiency` (default 0, which keeps the former results).

### Changed
- The `Module` base class is explicit: modules are built without arguments and configured with
  `update_params`, which returns the module; there is no class registry or `__init__` wrapping;
  the values of one call live in a single `_Call` context record; `fluid` is a validated
  property; plant files and checkpoints import classes only through `class_path`/`import_class`.
- Declaration listings recurse by default and key results by dotted path; `inlets()` and
  `outlets()` list the module's own ports. `health(result, measured)` receives the call's
  `ModuleResult`; `load_state_dict` takes `strict`; `has_input_value` and
  `clear_param_overrides` were added.
- Ports and controls follow one naming rule: `ProductionReservoir.production_rate` (was `m_dot`),
  `DoubletHeatPlant.secondary_in` (was `secondary`, also in `plant.json` and the data columns),
  `Doublet.return_in`/`supply_out` (were `return_stream`/`supply`) and
  `Boiler.temperature_setpoint` (was `setpoint_T`). `MissingMeasurement` became
  `gm.errors.MissingMeasurementError`, and costs are summed by
  `gemini.core.types.cost.total_cost(plant)` over modules that define `capex()`.
- Physics consists of plain functions with one unit table; `ConstantWater` became
  `FluidProperties`, and `Profile.constant(value, unit=, clock=)` is the only constant form.
- Runtime settings are context-local; ESP efficiency is a fraction; undefined radial
  diagnostics are reported as unavailable.
- `Blowdown` is a bleed split: `feed_in` -> `retained_out`, `blowdown_out` under the
  `blowdown_fraction` control (was a pass-through `inlet` -> `outlet` with a `modelled`
  output). `FlowCoefficient` allows zero, so a closed valve reports it.
- Dependencies are version ranges instead of exact pins: pandas >= 2.2.2, including pandas 3.
  Under pandas 3, results have a microsecond time index and `str` text columns, ambiguous local
  times raise `ValueError` instead of pytz's `AmbiguousTimeError`, and CSV decimals parse
  correctly rounded, which moves replays of the example data by up to 1.7e-13 relative (see
  `.claude/docs/refactor-notes.md`).

### Removed
- `gm.modules.list/get/create`, the module catalogue and engine registry, `Sequential`,
  `fidelity`, `apply`, `column_units`, `last_result(s)`, `Module.cost`, keyword-value
  construction, `runtime.dtype` and `runtime.manual_seed`, `gemini.design`, `gemini.agentic`, the
  legacy `nodes=` options and `plant.legacy_info`, `Results.save_csv/save_parquet`,
  `Dataset.frame/describe/reopen`, `Progress`, `AlarmCollector` and `Output(optional=)`.
- `BoosterPump` (a pass-through placeholder with `modelled=False`); use `CentrifugalPump`.
- The Flask interface, application/UI workflows, container stack, platform launcher scripts and
  UI-only dependencies.

### Fixed
- Engine: resume gives the same results as an uninterrupted run; daily clocks follow local
  midnight across DST; offset timestamps load across DST switches; the event log no longer turns
  NaN into errors and always removes its hooks; live runs anchor their grid at the committed
  position, reuse the checkpointed step for single rows and keep the caller's plant and error
  policy; NumPy integer durations are seconds; text time axes are accepted.
- Modules: redefining a module class or reusing a built-in class name no longer fails; assigned
  fluids are kept; slicing a `ModuleList` no longer re-paths its children; `UNSET` keeps its
  identity under copy and pickling.
- Physics: differences convert without unit offsets; the Beggs–Brill map covers its exact
  regime boundaries; two-phase reverse flow uses mirrored friction; zero flow, zero CO2, NaN and
  out-of-range inputs raise `PhysicsRangeError` instead of crashing; `Stream(flow="10")` raises
  `UnitError`.
- Legacy: conversion reads the in-memory project; `write_csv` writes midnight timestamps;
  calibration tolerates a NaN duty row; the t/h ESP head guess is correct; `check_wiring` works
  on a copy; `barg` converts from SI correctly; an ambiguous data CSV and unknown runtime keys
  raise explicit errors; mixed timestamp spellings parse.
- Data: replay, simulation and clocks work with timestamp indexes of any resolution (s, ms, us,
  ns). Under pandas 3, which parses text times as microseconds, the loader compared them with
  nanosecond tick values, so every tick looked like a gap and replay silently skipped every twin;
  `native_step` and clock durations were also 1000 times too short.
- Clocks: daily `Clock.days`/`Clock.year` steps follow local midnight across DST under pandas 3,
  which reads a `Timedelta` frequency as a fixed 24 hours.

## [1.0.3] - 2026-10-13
### Added
- parameters and tag names of the original doublet example using CSV data
### Fixed
- fix influxdb writing data float

## [1.0.2] - 2026-10-12
### Fixed
- fix grafana reverse-proxy authentication inside iframe

## [1.0.1] - 2026-08-20
### Fixed
- add python-dotenv package to pyproject.toml
### Changed
- more info for setting up environment variables in documentation
- change naming environment variables of OLLAMA and CHROMADB


## [1.0.0] - 2026-07-19

### Added
- Initial open-source release of the GEMINI Geothermal Suite.
- Initial release of the GEMINI Geothermal Model.
- Initial release of the GEMINI Geothermal Framework.
- Initial release of the GEMINI Geothermal Application.
  - Diagram Builder Application
  - ESP Monitoring Application
  - Productivity Application
  - Injectivity Application
  - Well Schematic Application
  - Well Integrity Monitoring Application
  - Time-series Visualization Application
  - Report Generation Application
  - Chatbot Application
- Initial release of the GEMINI Geothermal Interface.
