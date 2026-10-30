# Public API

Use `import gemini as gm`. This page lists **every public name**, frozen at `gm.__version__ = "0.1.0"`,
and is the page the other repositories build against. Names not listed here (a helper method such
as `Results.commit`, anything in `gm.utils`, any import of an internal path such as
`gemini.engine.results`) are internal and may change. `tests/unit/test_public_api.py` pins the names, their parameter names and the schema files.
Status is **real**, or **later**: the signature is final and the call raises
`gm.errors.NotImplementedYet`.

Conventions on every entry:

- Data returns are plain JSON: no NumPy types, NaN and infinity are `null`
  (`gemini.utils.jsonable.to_plain`), and `json.dumps(result, allow_nan=False)` works.
- Results are deterministic: the same input gives the same numbers on every backend.
- Inputs take a number in SI or a string such as `"150 m3/h"`. Every output is in SI and says its unit.
- A plant and an engine are not shared across threads: each worker loads its own.
- The documents exchanged between repositories have a JSON Schema and a sample in `docs/schemas/`:
  `module_description`, `plant_spec`, `results_summary`, `error`, `profile` (`<name>.schema.json`,
  `<name>.sample.json`). Regenerate with `python scripts/write_schemas.py`.

## Freeze rule

`gm.__version__` is the one version of the package, read from `version` in `pyproject.toml`.
Semantic versioning, below 1.0: a breaking change to a public name or return field raises the
minor number (`0.2.0`); an addition or a fix raises the patch number (`0.1.1`). Every change has a
line in the change log below, in the same commit. The public-API test compares against a stored
snapshot (`tests/fixtures/public_api.json`) that records the version and may only change together
with it; its hash per version is held in the test.

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
| `gm.streams.names()` | `brine`, `hot_water`, `chilled_water`, `gas`, `electricity`, `fuel` | real |

On a class or an instance of `Module` (and on what `gm.modules.get` returns):

| Name | Returns | Status |
| --- | --- | --- |
| `describe()` | see below; schema `module_description` | real |
| `parameter_schema()` | JSON Schema draft 2020-12; each property has `unit`, `quantity`; dotted child names | real |
| `validate_params(params)` | `[{path, message, code, suggestions?}]`, never raises | real |
| `help()` | text | real |

```text
{name, type, category, summary, doc,
 parameters, controls, boundaries, measured, state:
   {name: {type, unit, quantity, default, minimum, maximum, enum, description, section}},
 inlets, outlets: {port: {stream, fields: {m_dot: {unit}, T: {unit}, p: {unit}}}},
 outputs: {name: {unit, kind, soft_sensor}},
 children: {name: type},
 connections: [{source, target, stream, kind}],
 values: {parameters, controls, boundaries}}     on an instance only
```

`stream` is `null` for a port that takes any stream; `kind` is an additive quantity or `null`;
`measured` is every output of the module, which is what a `measured` binding may name. `minimum`
and `maximum` are the closest limit, strict or not. `values` are keyed by dotted path.

## Plants

Three levels and one representation: see [plants.md](plants.md). The spec schema is
`gm.plants.spec_schema()` and the plant file is the spec.

| Name | Returns | Status |
| --- | --- | --- |
| `gm.Plant(name)` | an empty plant, a normal composite `Module` | real |
| `p.add(kind, name=None, params=None)` | the added module; `kind` is a registry name or a class, `params` the dict `set_params` takes | real |
| `p.connect(source, target, kind=None)` | nothing; `ValidationError` with candidates, see [plants.md](plants.md) | real |
| `p.summary()` | text table | real |
| `p.validate()` | `[{path, message, code, suggestions}]` | real |
| `p.to_spec()`, `p.to_dict()` | the spec (one function) | real |
| `gm.plants.from_spec(spec)`, `from_dict(spec)` | a plant (one function); one `ValidationError` lists every problem | real |
| `gm.plants.validate(spec)` | `[{path, message, code, suggestions}]`, paths such as `connections[1].target`; never raises | real |
| `gm.plants.spec_schema()` | JSON Schema | real |
| `gm.plants.migrate(old)` | spec; every older stored format to format 2 | real |
| `gm.plants.names()` | plant names, the `plants` category | real |
| `gm.plants.get(name)` | a new plant without values | real |
| `gm.plants.example(name)` | a plant with real values | real |
| `gm.plants.templates()` | `[{name, title, description, purpose}]`, purpose `heating`, `cooling`, `both` | real |
| `gm.plants.from_template(name, parameters=None)` | a plant; `parameters` are `{"<id>.<param>": value, "<id>.enabled": bool}`, or sizes such as `{"producers": 3}` | real |
| `gm.plants.convert_legacy(folder)` | spec; expected files in [legacy.md](legacy.md) | real |
| `gm.plants.HeatingSubstation`, `CoolingSubstation`, `ATESPlant` | handwritten special cases, see [plants.md](plants.md) | real |

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

Run input is one format: a pandas DataFrame or a `gm.Dataset` with a timezone-aware UTC index,
columns named by binding `column`, units from the binding. A missing bound column raises
`ValidationError` (a `ValidationError`, code `missing_column`) listing them all. A NaN row is a row
code and the run continues.

```python
import gemini as gm

plant = gm.plants.example("DoubletHeatPlant")
results = gm.simulate(plant, profile)
```

Use the functions for a run that is one call (agents, backend workers, examples, scripts) and
`gm.Engine` for what must live across calls: a run held in memory, a callback that reads the
engine, a manual checkpoint. Each function builds an `Engine`, calls the matching method and
returns its `Results`, so the numbers are the same on every backend; see
[engine.md](engine.md#functions-or-engine).

| Name | Returns | Status |
| --- | --- | --- |
| `gm.simulate(plant, profile, clock=None, checkpoint=None, checkpoint_every=None, backend="numpy", callbacks=None, on_error="raise")` | `Results` | real |
| `gm.replay(plant, data, start=None, end=None, state=None, clock=None, only=None, checkpoint=None, checkpoint_every=None, backend="numpy", callbacks=None, on_error="raise")` | `Results`; `results.end_state` is the `state=` of the next call | real |
| `gm.live(plant, source, checkpoint, step=None, now=None, sink=None, backend="numpy", callbacks=None, on_error="raise")` | `Results` of the new rows; `checkpoint` is a required path | real |
| `gm.resume(checkpoint, callbacks=None)` | `Results` of an interrupted `simulate` or `replay`; `RunError` on a live checkpoint | real |
| `gm.Engine(plant, backend="numpy", callbacks=None, on_error="raise")` | one runner, for complex tasks | real |
| `engine.simulate(profile, clock=None)` | `Results` | real |
| `engine.replay(data, start=None, end=None, state=None, clock=None, only=None)` | `Results`; `results.end_state` is the `state=` of the next call | real |
| `engine.live(source, checkpoint=None, step=None, now=None, sink=None)` | `Results` of the new rows | real |
| `engine.save_checkpoint(path)`, `gm.Engine.load_checkpoint(path, callbacks=None)`, `engine.resume()` | see [engine.md](engine.md) | real |
| Callback `on_progress(engine, done, total)` | a callback may raise `gm.errors.Cancelled`; committed ticks stay in `engine.results` | real |
| `gm.evaluate(module, parameters, inlets, controls)` | `{outlets: {port: {field: {value, unit}}}, outputs: {name: {value, unit}}, errors: [error]}`, never raises for a failing call | real |

| `Results` | Returns | Status |
| --- | --- | --- |
| `names()` | `{path: [field]}` | real |
| `get(path, field, start=None, end=None)` | `{time, values, unit}` | real |
| `summary(path=None, start=None, end=None)` | `{path: {field: {min, max, mean, unit}}}`; schema `results_summary` | real |
| `errors()` | `[{timestamp, module, code, type, message}]`, `code` from `gm.errors.ROW_CODES` | real |
| `to_frame()` | DataFrame, columns `path.field`, the calculated-tag names | real |
| `to_dict()` | `{time, duration, series: {path: {field: {unit, values}}}, errors, skip_counts, end_state}` | real |
| `save(path)`, `gm.Results.load(path)` | `.npz` | real |
| `to_bytes()`, `gm.Results.from_bytes(data)` | `.npz` bytes | real |
| `end_state` | `{position, module_states}` | real |
| `energy_report()` | DataFrame of energy, peaks, hours, alarms and skips | real |
| `results[path].field`, `skip_counts` | a pandas Series, `{path: {reason: count}}` | real |

## Demand profiles

| Name | Returns | Status |
| --- | --- | --- |
| `gm.profiles.names()` | `heating_demand`, `cooling_demand` | real |
| `gm.profiles.get(name)` | run input, a UTC DataFrame with units in `attrs["units"]` | later: no demand data ships yet |
| `gm.profiles.profile_schema()` | JSON Schema of a profile file | real |

## Analysis

Details, inputs and units are in the docstrings and [economics.md](economics.md).

| Name | Returns | Status |
| --- | --- | --- |
| `gm.analysis.nodal(plant, well, conditions)` | `{well, units, cases: [{conditions, ipr, vlp, operating_point, error}]}` | real for production wells; later for injection |
| `gm.analysis.pump_curve(plant, pump, measured=None)` | manufacturer curve and measured points, head in Pa | real |
| `gm.analysis.corrosion_forecast(model, until)` | wall thickness over time, years left | real |
| `gm.analysis.injectivity(data, well)` | Hall integral, derivative, skin lines | later |
| `gm.analysis.calibrate_pump(plant, pump, measured)` | correction factors for `set_params` | later |
| `gm.analysis.calibrate_corrosion(logs)` | a model for `corrosion_forecast` | later |
| `gm.analysis.erosion(plant, well)` | wear of pump and tubing | later |
| `gm.analysis.fit_head_coefficients(flows, frequencies, heads, stage_count)` | six ESP head coefficients | real |
| `gm.analysis.fit_head_correction(measured, theoretical)` | `(slope, offset)` of the head correction | real |
| `gm.analysis.estimate_reservoir_pressure(flows, bottomhole_pressures)` | `(pressure, r_squared)` | real |
| `gm.analysis.estimate_conductance(hot_in_T, hot_out_T, cold_in_T, cold_out_T, m_dot_hot, m_dot_cold, *, cp_hot, cp_cold, arrangement)` | apparent UA of an exchanger | real |

## Economics, KPIs and checks

Every economics return is `{value, unit, reason, ...}`; a value the inputs cannot give is `null`
with a `reason`. No shipped module declares a cost yet, so a shipped plant gives `null` until
modules declare `capex()`.

| Name | Status |
| --- | --- |
| `gm.economics.Assumptions` | real; sourced defaults in [economics.md](economics.md), others `None` |
| `gm.economics.capex(plant, assumptions=None)` | real |
| `gm.economics.opex(plant, results, assumptions=None)` | real |
| `gm.economics.lcoh(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | real |
| `gm.economics.lcoc(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | real |
| `gm.economics.co2(plant, results, assumptions=None)` | real |
| `gm.economics.npv(plant, results, discount_rate=None, lifetime=None, assumptions=None)` | real |
| `gm.economics.payback(plant, results, assumptions=None)` | real |
| `gm.kpi.compute(plant, results)`, `gm.kpi.names()` | real: `heating_coverage`, `cooling_coverage`, `cop`, `peak_heat`, `peak_cold` |
| `gm.checks.energy_balance(results)`, `mass_balance(results)`, `bounds(plant, results)`, `run_all(plant, results)` | real, each `{name, passed, value, tolerance}`; they are ledger checks, see [economics.md](economics.md) |
| `gm.testing.check_module(cls, example=None)` | real; a report, never raises |
| `gm.optim.calibrate(plant, dataset, params, start=None, end=None, backend="numpy", apply=True)`, `CalibrationResult` | real |
| `gm.optim.minimize(plant, profile, variables, objective, constraints=None, evaluations=100)` | later |
| `gm.optim.sample(plant, profile, distributions, metrics, count, seed=0)` | later |

`gm.optim.calibrate` fits only through replay and returns a `CalibrationResult`. With `apply=True` a
successful fit replaces the current parameter as an explicit override and adds no dated snapshot.
Pass parameter objects declared `calibratable=True`, such as
`plant.get_parameter("heat_exchanger.ua")`.

## Errors

`gm.errors` holds seven public classes, listed with their use in [errors.md](errors.md): `GeminiError`
with `ValidationError`, `DefinitionError`, `PhysicsError`, `RunError`, `Cancelled` and
`NotImplementedYet`, and `GeminiWarning`. `to_dict()` is the problem
`{path, code, message, suggestions}` (schema `problem`), `CODES` the fixed `code` list and `ROW_CODES`
the row codes with their meaning. `error.problems` lists every problem of an error.

## Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1.0 | 2026-10-30 | First consistent API. |

Before 0.1.0 the API counted integer versions 1 to 5: the first frozen list, `category` as the
folder of a module, `gm.legacy` moved behind `gm.plants.convert_legacy`, the fits moved to
`gm.analysis` with one name per concept ([glossary.md](glossary.md)), and the run functions over
`gm.Engine`. Checkpoints and results files written before 0.1.0 do not load: they raise
`ValidationError` with code `old_format`.
