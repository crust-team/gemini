# GEMINI Geothermal Suite

Composable geothermal physics and digital twins, developed by TNO and partners in the Nieuwe
Warmte Nu programme. Python 3.11 and Pydantic v2. Equipment and plants share a `Module` API;
streams use SI, measured twins use independent boundaries, and scenarios chain predictions.

## Quickstart

From this checkout (the existing dataset directory is `geothermal_doublet`):

```bash
pip install poetry
poetry install --extras parquet
poetry run python - <<'PY'
from pathlib import Path
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.config.build import build_plant
from gemini.core.data.timeseries import CSVTimeSeries
from gemini.core.modes.history import replay, calibrate
folder = Path("datasets/geothermal_doublet")
config = load_gemini(folder)
plant = build_plant(config)
data = CSVTimeSeries(folder / "geothermal_example_dataset.csv").frame
print(replay(plant, config, data.iloc[:672]).to_frame().head())
print(calibrate(plant, config, data.iloc[:672], "heat_exchanger", ["ua"], apply=True))
PY
```

## Module API

```python
from gemini.core.modules import Boiler, Sequential
from gemini.core.types import Stream, WATER
from gemini.core.modules.balance import collect_flows

plant = Sequential(Boiler({"fuel": "electric", "capacity": 100000, "efficiency": 0.95}))
result = plant({"0": {"setpoint_T": 350}}, inlet=Stream(m_dot=10, T=300, p=1e6, fluid=WATER))
print(result.outputs.root["0"].duty)
print(collect_flows(result))
print(dict(plant.named_params()))
snapshot = plant.state_dict()
plant.load_state_dict(snapshot)
```

`Module` supports named children, recursive parameters, bounded calibration references,
validated state loading, hooks, optional health and stateful stepping. Plants are handwritten
Module subclasses: `__init__` registers children and `forward` connects typed streams.
`GeothermalExamplePlant` groups wells and ESP under `doublet`, with named surface equipment.
Configuration selects its type and dated parameters; the diagram only verifies wiring.
`Sequential` chains modules with one fluid inlet/outlet and retains child energy reports.

`core.types` supplies physical quantity aliases, immutable `Fluid`/`Stream`, electricity/fuel/heat
reporting flows, UTC `Profile` inputs and sourced `Cost` estimates. See the
[types guide](.claude/docs/types.md) and [small composition example](examples/10_custom_plant.py).

Equipment declares `fidelity`: established correlations use `model`, filters and injection
pumps use `simple`, and liquid-only degassing/booster/blowdown use `passthrough`. Gas separation
is not modelled. Bindings and sensor names belong to configuration, not equipment.

## Execution and persistence

- `history.replay`: independent measured-boundary twins, with dated parameters and counted skips.
- `history.calibrate`: bounded least squares on an explicit window; `apply=False` by default.
- `live.run_latest`: the same twin evaluator over a driver's `latest(window)` result or loaded CSV.
- `scenario.run`: chained assumptions, optionally advancing process state.
- `Results.to_frame`: `(module_path, field)` columns; CSV and optional Parquet exports.
- `EventLog(path).attach(plant)`: JSON-lines forward traces; `EventLog()` retains them in memory.
- `build_plant`, `plant_to_config`, `save_config`, `load_config`: portable JSON design round trips.

The original CSV, InfluxDB and AVEVA drivers remain available. A live source adapter must expose
`latest(window)` as a timestamp-indexed DataFrame; external services are not needed for examples.

## Examples and validation

`examples/01`–`05` demonstrate individual equipment, a manual chain and discovery;
`06` imports/exports a handwritten plant, `07` replays a week, `08` calibrates HX conductance and `09` runs a day.
`10` defines a custom doublet/HX/boiler plant. All ten run in the test suite.

```bash
poetry run black --check gemini tests examples
poetry run isort --check-only gemini tests examples
poetry run flake8 gemini tests examples
poetry run pytest tests
```

The full 17,280-row e2e test runs by default. AVEVA requires credentials; Parquet requires the
`parquet` extra. The 25 original physics cases and eight captured monitoring outputs are immutable.

## Accuracy and limits

The example has **zero unmapped properties/tags** and 100% coverage for its eight bound twins.
The three remaining equipment nodes lack measured inlet boundaries and run in scenarios. Health
with `assessed=False` means the model or measurements cannot support a diagnostic.

The supplied ESP power curve is all zeros, and its head curve disagrees with the CSV by 63.2%
median. These produce alarms even though all source status labels say Normal. Calibrated HX
holdout duty error is 0.63% median; the hot temperature maximum is 0.566 K. Full-chain pressure
and duty errors remain 57.6% and 12.4%. The e2e tests document these exceptions explicitly;
green tests do not establish the original accuracy targets. The plant imposes flow and does
not solve hydraulic operating-point balance.

Read [AGENTS.md](AGENTS.md), [numerical decisions](.claude/docs/refactor-notes.md), and the
[implementation report](docs/module-refactor-report.md) before changing the models.

The types refactor preserves all prior numerical reconciliation results. On 100 sampled rows,
mass and modeled thermal transfers close. **Strict energy closure does not**: isothermal pumps
leave about 212 kW median electrical power unallocated. Total electricity median error is
38.73% on measured boundaries and 29.80% in the full chain; the supplied ESP power curve remains
zero. `energy_balance` exposes both residual and unresolved power; no heat loss is invented.
See the [types refactor report](docs/types-refactor-report.md) for the complete before/after audit.
