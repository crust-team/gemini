# Public API

Use `import gemini as gm`. This page lists **every public name** at `gm.__version__ = "0.2.0"`, and
is the page the other repositories build against. Names not listed here (a helper method such as
`Results.commit`, anything in `gm.utils`, any import of an internal path such as
`gemini.engine.results`) are internal and may change. `tests/unit/test_public_api.py` pins the
names, their parameter names and the schema files, and `tests/integration/test_return_shapes.py`
walks the returns of this page against their schemas. Status is **real**, or **later**: the signature
is final and the call raises `gm.errors.NotImplementedYet`.

Conventions on every entry:

- Results are deterministic: the same input gives the same numbers on every backend.
- Inputs take a number in SI or a string such as `"150 m3/h"`. Outputs are in SI by default.
- A plant and an engine are not shared across threads: each worker loads its own.
- The documents exchanged between repositories have a JSON Schema and a sample in `docs/schemas/`:
  `value`, `problem`, `check`, `module_description`, `plant_spec`, `results_summary`, `profile`
  (`<name>.schema.json`, `<name>.sample.json`). Regenerate with `python scripts/write_schemas.py`.

## Return shapes

Every public return that carries data uses only three shapes, defined once in `gemini/types/shapes.py`
and built by one helper each, so no module assembles them by hand. Returns are plain JSON: no NumPy
types, NaN and infinity are `null` (`gemini.utils.jsonable.to_plain`), and
`json.dumps(result, allow_nan=False)` works.

1. **Value** `{value, unit}`. `value` is a number, an array or `null`; when it is `null`, a `reason`
   key says why. The key is `value` for arrays too. A time series is a value with a `time` key
   beside it: `{time, value, unit}`. Statistics are `{min, max, mean}`, each a value. An output that
   is a flag or a text keeps its boolean or string. An economics value adds the parts of its result
   as more keys, each a value or a text.
2. **Problem** `{path, code, message, suggestions}`, for every error, validation result and failed
   run row. A run row adds `time`. There is no `class` key: `code` is the stable key for machines.
3. **Check** `{name, passed, value, limit}`, where `value` and `limit` are values. A failed check is
   an answer, not an error. `passed` is `null`, with the reason in `value`, when there is nothing to
   judge.

A number always travels with its unit in the same dict: there is no separate `units` map. Counts of
skips by reason (`skip_counts`, `reasons`) and the state trees of `end_state` are the input of a next
call or plain tallies, not values. Public returns are plain dicts: a DataFrame comes only from a
method named `to_frame`, the one exception being run input (`gm.profiles.get`), because the run-input
format is a DataFrame. Text comes only from `help()` and `summary()` of a plant, meant for people.

## Output units

Outputs stay SI by default. Every call marked *units* below takes an optional `units` argument, a map
from quantity to unit: `results.get("hx", "duty", units={"power": "MW"})`. Conversion uses `gm.units`
only, on the way out; nothing inside the run changes, and the returned `unit` keys say the unit
actually used (`frame.attrs["units"]` on a table). A key reaches the quantities of its family, the
first quantity defined with the same SI unit leading it: `power` reaches `duty`, `electricity` and
`heat_loss`, `pressure` a pressure difference, `temperature` a temperature difference. A key of the
quantity itself wins. A difference converts by scale only. An unknown quantity, or a unit that does
not fit it, raises `ValidationError` with suggestions.

## Freeze rule

`gm.__version__` is the one version of the package, read from `version` in `pyproject.toml`.
Semantic versioning, below 1.0: a breaking change to a public name or return field raises the
minor number (`0.2.0`); an addition or a fix raises the patch number (`0.1.1`). Every change has a
line in the change log below, in the same commit. The public-API test compares against a stored
snapshot (`tests/fixtures/public_api.json`) that records the version and may only change together
with it; its hash per version is held in the test.

**Module catalogue.** Adding, removing, moving or renaming modules is never a version matter. The
snapshot covers the package API (functions, types, return shapes), not the list of modules.

## Package

| Name | Returns | Status |
| --- | --- | --- |
| `gm.__version__` | text, the version in `pyproject.toml` | real |
| `gm.Stream`, `gm.Ports`, `gm.Fluid`, `gm.BRINE`, `gm.WATER`, `gm.Quantity`, `gm.Profile`, `gm.Clock`, `gm.Dataset` | see [types.md](types.md), [data.md](data.md), [engine.md](engine.md) | real |
| `gm.no_outputs()`, `gm.runtime` | see [modules.md](modules.md), [runtime.md](runtime.md) | real |

## Modules and streams

| Name | Returns | Status |
| --- | --- | --- |
| `gm.modules.names(category=None)` | sorted registry names; spec plants have category `plants` | real |
| `gm.modules.get(name)` | the class; a spec plant gives a new plant. Unknown: `ValidationError` with `suggestions` | real |
| `gm.modules.categories()` | `subsurface`, `wells`, `pumps`, `treatment`, `exchangers`, `heating`, `cooling`, `power`, `storage`, `piping`, `demand`, `control`, `plants`, in display order; each is the folder that holds the module | real |
| `gm.modules.register(cls)` | `cls`, now in the registry; it states `category = "<one of the list>"`; a taken name is refused | real |
| `gm.modules.load_file(path)` | names of the `Module` classes of a Python file that state a `category`, registered | real |
| `gm.modules.<Equipment>`, `Module`, `ModuleList`, `ModuleDict`, `collect_flows`, `emissions`, `energy_balance`, `mass_balance`, `trace_wiring` | classes and one-call audits, see [equipment.md](equipment.md) | real |
| `gm.modules.Boiler`, `ElectricBoiler`, `CHP`, `Flare`, `GasGrid`, `GasMakeup` | the gas chain: `boiler.fuel_in`, `boiler.gas_out`, see [equipment.md](equipment.md) | real |
| `gm.streams.names()` | `brine`, `hot_water`, `chilled_water`, `gas`, `electricity`, `fuel` | real |

On a class or an instance of `Module` (and on what `gm.modules.get` returns):

| Name | Returns | Status |
| --- | --- | --- |
| `describe()` | see below; schema `module_description` | real |
| `parameter_schema()` | JSON Schema draft 2020-12; each property has `unit`, `quantity`; dotted child names | real |
| `validate_params(params, on_error="raise")` | `[]`, or raises every problem; with `"record"` the list of problems | real |
| `help()` | text | real |

```text
{name, type, category, summary, doc,
 parameters, controls, boundaries, measured, state:
   {name: {type, unit, quantity, default, minimum, maximum, enum, description, section}},
 inlets, outlets: {port: {kind, fields: {m_dot: {unit}, T: {unit}, p: {unit}}}},
 outputs: {name: {unit, quantity, soft_sensor}},
 children: {name: type},
 connections: [{source, target, kind, type}],
 values: {parameters, controls, boundaries}}     on an instance only
```

`kind` is `null` for a port that takes any stream; an output's `quantity` is an additive quantity or `null`;
`measured` is every output of the module, which is what a `measured` binding may name. `minimum`
and `maximum` are the closest limit, strict or not. `values` are keyed by dotted path.

## Plants

Three levels and one representation: see [plants.md](plants.md). The spec schema is
`gm.plants.spec_schema()` and the plant file is the spec.

| Name | Returns | Status |
| --- | --- | --- |
| `gm.Plant(name)` | an empty plant, a normal composite `Module` | real |
| `p.add(type, name=None, params=None)` | the added module; `type` is a registry name or a class, `params` the dict `set_params` takes | real |
| `p.connect(source, target, type=None)` | nothing; `ValidationError` with candidates, see [plants.md](plants.md) | real |
| `p.summary()` | text table | real |
| `p.validate(on_error="raise")` | as `gm.plants.validate` | real |
| `p.to_spec()`, `p.to_dict()` | the spec (one function) | real |
| `gm.plants.from_spec(spec)`, `from_dict(spec)` | a plant (one function); one `ValidationError` carries every problem in `problems` | real |
| `gm.plants.validate(spec, on_error="raise")` | `[]`, or raises every problem; with `"record"` the list of problems, paths such as `connections[1].target` | real |
| `gm.plants.spec_schema()` | JSON Schema | real |
| `gm.plants.migrate(old)` | spec; every older stored format to format 2 | real |
| `gm.plants.names()` | plant names, the `plants` category | real |
| `gm.plants.get(name)` | a new plant without values | real |
| `gm.plants.example(name)` | a plant with real values | real |
| `gm.plants.templates()` | `[{name, title, description, purpose}]`, purpose `heating`, `cooling`, `both` | real |
| `gm.plants.from_template(name, parameters=None)` | a plant; `parameters` are `{"<id>.<param>": value, "<id>.enabled": bool}`, or sizes such as `{"producers": 3}` | real |
| `gm.plants.convert_legacy(folder)` | spec; expected files in [legacy.md](legacy.md) | real |
| `gm.plants.HeatingSubstation`, `CoolingSubstation`, `ATESPlant`, `Doublet` | handwritten special cases, see [plants.md](plants.md); a `Doublet` takes a design from its depth | real |

On any plant, `path` being a dotted module path (`""` is the root):

| Name | Returns | Status |
| --- | --- | --- |
| `set_params(path, params, valid_from=None)` | dated entry, validated; a complete snapshot | real |
| `params_at(path, time=None)` | `{name: value}` in force at `time`, latest without one | real |
| `param_history(path)` | `[{valid_from, params}]` | real |
| `bindable(path)` | `{controls: [name], boundaries: [name], inlets: {port: [field]}, measured: [name], state: [name]}` | real |
| `set_bindings(path, bindings)` | replaces them; flat `{name: column}` or `{name: {column, unit}}`, `name` a declaration or `port.field`; units checked | real |
| `get_module(path)`, `named_modules()` | a module, `(path, module)` pairs | real |
| `save(path)`, `Module.load(path)` | writes or reads the spec as JSON | real |

## Units

| Name | Returns | Status |
| --- | --- | --- |
| `gm.units.names(quantity=None)` | unit names, of one quantity if given | real |
| `gm.units.parse(text)` | `(value, unit)` | real |
| `gm.units.convert(value, from_unit, to_unit, quantity=None)` | number | real |
| `gm.units.fits(unit, quantity)` | bool; an unknown unit is false, an unknown quantity raises | real |

## Running

Run input is one format: a pandas DataFrame or a `gm.Dataset` with a timezone-aware UTC index, columns
named by binding `column`, units from the binding. A missing bound column raises `ValidationError`
(code `missing_column`) listing them all. A NaN row is a row code and the run continues.

```python
import gemini as gm

plant = gm.plants.example("DoubletHeatPlant")
results = gm.simulate(plant, profile)
print(results.summary(units={"power": "MW", "temperature": "degC"}))
```

Use the functions for a run that is one call (agents, backend workers, examples, scripts) and
`gm.Engine` for what must live across calls: a run held in memory, a callback that reads the engine,
a manual checkpoint. Each function builds an `Engine`, calls the matching method and returns its
`Results`, so the numbers are the same on every backend; see
[engine.md](engine.md#functions-or-engine).

| Name | Returns | Status |
| --- | --- | --- |
| `gm.schedule(plant, demand, rules)` | run input, a UTC DataFrame: the demand and one column per scheduled control, named after its dotted path; `operating_days` other than `None` raises `NotImplementedYet`; see [engine.md](engine.md#schedule) | real |
| `gm.simulate(plant, profile, clock=None, checkpoint=None, checkpoint_every=None, backend="numpy", callbacks=None, on_error="raise")` | `Results` | real |
| `gm.replay(plant, data, start=None, end=None, state=None, clock=None, only=None, checkpoint=None, checkpoint_every=None, backend="numpy", callbacks=None, on_error="raise")` | `Results`; `results.end_state` is the `state=` of the next call | real |
| `gm.live(plant, source, checkpoint, step=None, now=None, sink=None, backend="numpy", callbacks=None, on_error="raise")` | `Results` of the new rows; `checkpoint` is a required path | real |
| `gm.resume(checkpoint, callbacks=None)` | `Results` of an interrupted `simulate` or `replay`; `RunError` (code `checkpoint`) on a live checkpoint | real |
| `gm.Engine(plant, backend="numpy", callbacks=None, on_error="raise")` | one runner, for complex tasks | real |
| `engine.simulate(profile, clock=None)` | `Results` | real |
| `engine.replay(data, start=None, end=None, state=None, clock=None, only=None)` | `Results`; `results.end_state` is the `state=` of the next call | real |
| `engine.live(source, checkpoint=None, step=None, now=None, sink=None)` | `Results` of the new rows | real |
| `engine.save_checkpoint(path)`, `gm.Engine.load_checkpoint(path, callbacks=None)`, `engine.resume()` | see [engine.md](engine.md) | real |
| `AutoCheckpoint(path, every=100)` | a callback that saves every N steps or every duration | real |
| Callback `on_progress(engine, done, total)` | a callback may raise `gm.errors.Cancelled`; committed ticks stay in `engine.results` | real |
| `gm.evaluate(module, parameters, inlets, controls, on_error="raise", units=None)` | `{outlets: {port: {field: value}}, outputs: {name: value}, errors: [problem]}`; *units*; a run at one point | real |

| `Results` | Returns | Status |
| --- | --- | --- |
| `names()` | `{path: [field]}` | real |
| `get(path, field, start=None, end=None, units=None)` | the time series `{time, value, unit}`; *units* | real |
| `summary(path=None, start=None, end=None, units=None)` | `{path: {field: {min, max, mean}}}`, each a value; *units*; schema `results_summary` | real |
| `errors()` | `[{path, code, message, suggestions, time}]`, `code` from `gm.errors.ROW_CODES` | real |
| `to_frame(units=None, table="series")` | DataFrame. `"series"`: columns `path.field`, the calculated-tag names, *units*, with `attrs["units"]`. `"energy"`: the table of `energy_report`, one row per module and energy output | real |
| `to_dict(units=None)` | `{time, duration, series: {path: {field: value}}, errors, skip_counts, end_state}`, `duration` a value; *units* | real |
| `save(path)`, `gm.Results.load(path)` | `.npz` | real |
| `to_bytes()`, `gm.Results.from_bytes(data)` | `.npz` bytes | real |
| `end_state` | `{position, module_states}` | real |
| `energy_report(units=None)` | `{path: {output: {energy, peak, hours, operating_hours, alarms, alarm_rate, skipped, errors, peaks, reasons}}}`, every number a value; *units*. A path without an energy output has the entry `""` | real |
| `results[path].field`, `skip_counts` | a pandas Series, `{path: {reason: count}}` | real |

## Demand profiles

| Name | Returns | Status |
| --- | --- | --- |
| `gm.profiles.names()` | `heating_demand`, `cooling_demand` | real |
| `gm.profiles.get(name)` | run input, a UTC daily DataFrame of 365 rows in W, with `units` and the source file in `attrs`, the one DataFrame outside `to_frame` | real |
| `gm.profiles.profile_schema()` | JSON Schema of what `get` returns, as a document | real |

## Analysis

Details and inputs are in the docstrings and [economics.md](economics.md). Every number of these
returns is a value; every entry here takes *units*, except where a coefficient has no quantity.

| Name | Returns | Status |
| --- | --- | --- |
| `gm.analysis.nodal(plant, well, conditions, on_error="raise", units=None)` | `{well, cases: [{conditions, ipr: {rate, pressure}, vlp: {rate, pressure}, operating_point: {rate, wellhead_pressure, sandface_pressure}, error}]}`; with `"record"` a failed case has its problem in `error` | real for production wells; later for injection |
| `gm.analysis.pump_curve(plant, pump, measured=None, units=None)` | `{pump, frequency, curve: {flow, head}, measured: [{flow, frequency, head, theoretical_head}], correction: {slope, offset}}`, or `correction` a null value with its reason | real |
| `gm.analysis.corrosion_forecast(model, until, units=None)` | `{correlation, rate, thickness, minimum_thickness, years_left}`; `thickness` a time series, `rate` stays in mm/year | real |
| `gm.analysis.injectivity(data, well, units=None)` | Hall integral, derivative, skin lines | later |
| `gm.analysis.calibrate_pump(plant, pump, measured)` | correction factors for `set_params` | later |
| `gm.analysis.calibrate_corrosion(logs)` | a model for `corrosion_forecast` | later |
| `gm.analysis.erosion(plant, well, units=None)` | wear of pump and tubing | later |
| `gm.analysis.fit_head_coefficients(flows, frequencies, heads, stage_count, units=None)` | a value of six ESP head coefficients, on their own basis | real |
| `gm.analysis.fit_head_correction(measured, theoretical, units=None)` | `{slope, offset}` of the head correction | real |
| `gm.analysis.estimate_reservoir_pressure(flows, bottomhole_pressures, units=None)` | `{pressure, r_squared}` | real |
| `gm.analysis.estimate_conductance(hot_in_T, hot_out_T, cold_in_T, cold_out_T, m_dot_hot, m_dot_cold, *, cp_hot, cp_cold, arrangement, units=None)` | a value of the apparent UA of an exchanger | real |

## Economics, KPIs and checks

Every economics function takes `(plant, results, ...)`, only `capex` has no results, and returns a
value with the parts of the result as more keys. A value the inputs cannot give raises
`ValidationError` (code `no_value`, or `missing_assumption` for an assumption nobody gave); with
`on_error="record"` it is `{value: null, unit, reason}`. Equipment declares `capex(assumptions)` from
its design values and the cost factors of `Assumptions`, see [economics.md](economics.md).

| Name | Status |
| --- | --- |
| `gm.economics.Assumptions` | real; sourced defaults in [economics.md](economics.md), others `None` |
| `gm.economics.capex(plant, assumptions=None, on_error="raise")` | real |
| `gm.economics.opex(plant, results, assumptions=None, on_error="raise")` | real |
| `gm.economics.lcoh(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise")` | real |
| `gm.economics.lcoc(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise")` | real |
| `gm.economics.co2(plant, results, assumptions=None, on_error="raise")` | real |
| `gm.economics.npv(plant, results, discount_rate=None, lifetime=None, assumptions=None, on_error="raise")` | real |
| `gm.economics.payback(plant, results, assumptions=None, on_error="raise")` | real |
| `gm.kpi.compute(plant, results)`, `gm.kpi.names()` | real: `{name: value}` of `heating_coverage`, `cooling_coverage`, `cop`, `peak_heat`, `peak_cold` |
| `gm.checks.energy_balance(results)`, `mass_balance(results)`, `bounds(plant, results)` | real, each a check; they are ledger checks, see [economics.md](economics.md) |
| `gm.checks.run_all(plant, results)` | real: `{passed, checks: [check]}` |
| `gm.checks.Limits()`, `add(target, min=None, max=None)`, `to_dict()`, `from_dict(data)` | real: limits of `"<path pattern>.<output>"`, built without a plant; a plain dictionary |
| `gm.checks.limits(plant, results, limits)` | real: a list of checks, one per matched module and output, `value` the worst of the run; an unmatched pattern raises `ValidationError` code `unknown_name` |
| `gm.testing.check_module(cls, example=None)` | real; for developers of a new module class only: a report, never raises |
| `gm.optim.calibrate(plant, dataset, params, start=None, end=None, backend="numpy", apply=True)`, `CalibrationResult` | real |
| `gm.optim.minimize(plant, profile, variables, objective, constraints=None, evaluations=100)` | later |
| `gm.optim.sample(plant, profile, distributions, metrics, count, seed=0)` | later |

`gm.optim.calibrate` fits only through replay and returns a `CalibrationResult`. With `apply=True` a
successful fit replaces the current parameter as an explicit override and adds no dated snapshot.
Pass parameter objects declared `calibratable=True`, such as
`plant.get_parameter("heat_exchanger.thermal_conductance")`.

## Errors

Every public call raises on failure by default. A call that can report instead takes
`on_error="raise" | "record"`: `validate` functions return the problems, `gm.evaluate` returns them
under `errors`, a run records them in `results.errors()` and continues, an economics value is
`{value: null, reason}`. `gm.checks.*` return a check; a violated limit never raises.

`gm.errors` holds seven public classes, listed with their use in [errors.md](errors.md):
`GeminiError` with `ValidationError`, `DefinitionError`, `PhysicsError`, `RunError`, `Cancelled` and
`NotImplementedYet`, and `GeminiWarning`. `to_dict()` is the problem
`{path, code, message, suggestions}` (schema `problem`), `error.problems` lists every problem of an
error, `CODES` is the fixed `code` list and `ROW_CODES` the row codes with their meaning.

## Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.2.0, unreleased changes | | Port names follow `<role>_in` and `<role>_out` (`gm.plants.migrate` converts stored specs). `Inlet(Stream, kind=...)` replaces `stream=`, the first argument of a declaration is `type`, `p.add(type, ...)`, `p.connect(source, target, type=None)`, a connection's `type: "state"`; `describe()` gives ports `{kind, fields}`, outputs `{unit, quantity, soft_sensor}`, connections `{source, target, kind, type}`. |
| 0.2.0, unreleased changes | | Layout: helpers in `gemini/modules/_utils/`, physics of one category in its `_physics.py`. Public names unchanged. |
| 0.2.0 | 2026-10-31 | Demand profiles: `gm.profiles.get` reads the two organiser files of 2027; `profile_schema` describes what `get` returns. |
| 0.2.0 | 2026-10-31 | No dangling ports: an unconnected port is `unconnected_port`; plant ports exist only when named, the automatic `<path>_<port>` ports are gone. |
| 0.2.0 | 2026-10-31 | A module may set its children's values: every parameter route reaches an overridden `set_params`; `to_dict` stores no derived value. |
| 0.2.0 | 2026-10-31 | `Fluid`: `density` and `viscosity` replace `liquid_density` and `liquid_viscosity`; `gas_liquid_ratio`, `gas_composition`, `kind="gas"`; reservoirs lose both parameters. |
| 0.2.0 | 2026-10-31 | Gas chain: `Boiler` and `CHP` get `fuel_in` and `gas_out`; `ElectricBoiler` replaces `fuel_type="electric"`; `GasGrid`, `GasMakeup`, `Flare`; `gm.economics.co2` sums the emission outputs; `gas_price` and `methane_gwp` replace `fuel_price` and `fuel_emission_factor`; code `missing_assumption`. |
| 0.2.0 | 2026-10-31 | `gm.plants.Doublet`: a doublet designed from its depth; `gm.modules.get("Doublet")` gives that class. |
| 0.2.0 | 2026-10-31 | Two-phase well check: the gas superficial velocity follows the gas mass flow, at the gas density of the section. |
| 0.2.0 | 2026-10-31 | `gm.schedule`; a root inlet field binds to a column named `port.field`. |
| 0.2.0 | 2026-10-31 | `gm.checks.Limits` and `gm.checks.limits`; `Doublet.flow`, `Doublet.brine_cooling`, `HeatConsumer.supply_in_T`, `ProductionReservoir.liquid_flow`, `InjectionWell.wellhead_temperature`, `Output.difference`. |
| 0.2.0 | 2026-10-31 | Costs: `capex(assumptions)` on equipment, cost factors in `Assumptions`, `heat_cost_share`. |
| 0.2.0 | 2026-10-31 | Hackathon example `examples/plants/simulate/04_hackathon_plant.py`. |
| 0.2.0 | 2026-10-31 | Version 0.2.0: a checkpoint written before 0.2.0 raises `old_format`; `gm.plants.migrate` converts its plant file. |
| 0.1.0 | 2026-10-30 | First consistent API. |

Before 0.1.0 the API counted integer versions 1 to 5: the first frozen list, `category` as the
folder of a module, `gm.legacy` moved behind `gm.plants.convert_legacy`, the fits moved to
`gm.analysis` with one name per concept ([glossary.md](glossary.md)), and the run functions over
`gm.Engine`. Checkpoints and results files written before 0.1.0 do not load: they raise
`ValidationError` with code `old_format`.
