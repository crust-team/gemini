# Engine refactor report

Implemented locally on `refactor/engine`; no push or PR. This follows the types phase and
preserves its physical models, source dataset, two original golden JSON files, and every
previous reconciliation metric. Full-dataset replay remains below the 60-second limit.

## 1. Final package and test trees

Package files, including three levels below `core/`:

```text
gemini/
├── agentic/
│   └── __init__.py
├── core/
│   ├── config/
│   │   ├── __init__.py
│   │   ├── build.py
│   │   ├── gemini_loader.py
│   │   ├── io.py
│   │   ├── param_mapping.py
│   │   ├── schema.py
│   │   └── wiring.py
│   ├── data/
│   │   ├── drivers/
│   │   │   ├── __init__.py
│   │   │   ├── avevadb_driver.py
│   │   │   ├── csv_driver.py
│   │   │   ├── csv_memory.py
│   │   │   ├── database_driver_abstract.py
│   │   │   ├── database_reader_abstract.py
│   │   │   ├── influxdb_aveva_reader_db.py
│   │   │   ├── influxdb_csv_reader_db.py
│   │   │   ├── influxdb_driver.py
│   │   │   └── sources.py
│   │   ├── __init__.py
│   │   ├── dataset.py
│   │   └── loader.py
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── callbacks.py
│   │   ├── checkpoint.py
│   │   ├── clock.py
│   │   ├── engine.py
│   │   ├── registry.py
│   │   ├── results.py
│   │   └── step.py
│   ├── modules/
│   │   ├── heat/
│   │   │   ├── __init__.py
│   │   │   ├── boiler.py
│   │   │   └── heatexchanger.py
│   │   ├── plants/
│   │   │   ├── __init__.py
│   │   │   ├── doublet.py
│   │   │   └── geothermal_example.py
│   │   ├── pumps/
│   │   │   ├── __init__.py
│   │   │   ├── boosterpump.py
│   │   │   ├── esp.py
│   │   │   └── injectionpump.py
│   │   ├── subsurface/
│   │   │   ├── __init__.py
│   │   │   ├── injectionwell.py
│   │   │   ├── productionwell.py
│   │   │   └── reservoir.py
│   │   ├── treatment/
│   │   │   ├── __init__.py
│   │   │   ├── blowdown.py
│   │   │   ├── degasser.py
│   │   │   └── filter.py
│   │   ├── __init__.py
│   │   ├── balance.py
│   │   ├── catalogue.py
│   │   ├── module.py
│   │   └── wiring.py
│   ├── physics/
│   │   ├── __init__.py
│   │   ├── chemistry.py
│   │   ├── constants.py
│   │   ├── corrosion.py
│   │   ├── erosion.py
│   │   ├── fluid.py
│   │   ├── geometry.py
│   │   ├── heat_transfer.py
│   │   ├── hydraulics.py
│   │   ├── pumps.py
│   │   └── units.py
│   ├── types/
│   │   ├── __init__.py
│   │   ├── bindings.py
│   │   ├── cost.py
│   │   ├── flows.py
│   │   ├── fluid.py
│   │   ├── profile.py
│   │   ├── quantities.py
│   │   └── results.py
│   └── __init__.py
├── design/
│   └── __init__.py
├── optim/
│   ├── __init__.py
│   └── calibrate.py
└── __init__.py
```

```text
tests/
├── core/
│   ├── config/
│   │   ├── test_config.py
│   │   └── test_param_mapping.py
│   ├── data/
│   │   ├── credentials/
│   │   │   └── avevadb_TEMPLATE.json
│   │   ├── __init__.py
│   │   ├── test_avevadb_driver.py
│   │   └── test_dataset_loader.py
│   ├── engine/
│   │   ├── reference/
│   │   │   ├── replay.pkl
│   │   │   └── simulate.pkl
│   │   ├── test_engine.py
│   │   └── test_registry.py
│   ├── modules/
│   │   ├── heat/
│   │   │   ├── test_boiler.py
│   │   │   └── test_heatexchanger.py
│   │   ├── pumps/
│   │   │   ├── test_boosterpump.py
│   │   │   ├── test_esp.py
│   │   │   └── test_injectionpump.py
│   │   ├── subsurface/
│   │   │   ├── test_injectionwell.py
│   │   │   ├── test_productionwell.py
│   │   │   └── test_reservoir.py
│   │   ├── treatment/
│   │   │   ├── test_blowdown.py
│   │   │   ├── test_degasser.py
│   │   │   └── test_filter.py
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
├── optim/
│   └── test_calibrate.py
├── __init__.py
├── test_examples.py
├── test_public_api.py
└── test_quickstart.py
```

## 2. Deleted, moved and extracted paths

- Deleted `gemini/core/modes/` completely. Its `twin.py` moved to `engine/step.py`; the
  calibration portion of `history.py` moved to `optim/calibrate.py`. Historical replay,
  live windows and scenarios now share `Engine._run`; mode-specific runner files are gone.
- `engine/events.py` moved to `engine/callbacks.py` and gained lifecycle callbacks.
- All three `data/connector/*_driver.py` files moved to `data/drivers/`, along with
  `database_driver_abstract.py`, `database_reader_abstract.py`, `influxdb_aveva_reader_db.py`,
  `influxdb_csv_reader_db.py` and `csv_memory.py`. Their imports were updated.
- Removed `data/timeseries.py`; its callers now use `Dataset.from_csv`.
- Discovery moved from `engine/registry.py` into `modules/catalogue.py`, and wiring observation
  from `config/wiring.py` into `modules/wiring.py`. The requested engine registry and configuration
  verification entrypoints expose the same module-owned operations; no removed mode is shimmed.
- Binding/date schemas were extracted into `types/bindings.py` so module ownership does not
  create upward imports. The config layer registers the serializer used by `Module.save`.
- `tests/core/modes/test_modes.py` moved/expanded into `tests/core/engine/test_engine.py`;
  calibration coverage lives in `tests/optim/test_calibrate.py`. All moves used `git mv`.

## 3. Acceptance script and output

[examples/00_quickstart.py](../examples/00_quickstart.py) preserves every requested call shape.
`tests/test_quickstart.py` executes that exact file in an isolated directory, verifies the
17,280 replay rows and exact resumed frame, 24 simulation ticks, successful applied fit,
plant JSON round-trip, and 97 fresh live rows. `tests/test_examples.py` executes it again
alongside all twelve other examples.

Only repository-specific names changed:

- `datasets/geothermal_example` → `datasets/geothermal_doublet`. AGENTS.md and the existing
  filesystem require retaining this folder name; there is no geothermal_example directory.
- `doublet.hx` → `heat_exchanger`; the real ESP path remains `doublet.esp`.
- `production_rate` → `Qp`, and `esp_frequency` → `ESP_freq`, matching root sensor columns.

The package was installed editable into the existing Python 3.11 environment using
`pip install --no-deps --no-build-isolation --no-index -e .`; no network installation was used.
Captured stdout (also [a separate artifact](engine-quickstart-output.txt)):

```text
GeothermalExamplePlant(
  (doublet): Doublet(
    (reservoir): ProductionReservoir(role=production, pressure=220 bar, temperature=80 °C, permeability=9.8692e-12 m2)
    (well): ProductionWell(segment=below_esp, esp_depth=600 m, soil_temperature=15 °C, u_value=10 W/m2/K)
    (esp): ESP(no_stages=15, setting_depth=600 m, motor_efficiency=1, bep_flow=129.98 m3/h)
    (riser): ProductionWell(segment=above_esp, esp_depth=600 m, soil_temperature=15 °C, u_value=10 W/m2/K)
    (injector): InjectionWell(friction_correlation=darcy_weisbach, friction_correlation_2p=BeggsBrill, soil_temperature=15 °C, u_value=10 W/m2/K)
    (sink): InjectionReservoir(role=injection, pressure=220 bar, temperature=80 °C, permeability=9.8692e-12 m2)
  )
  (degasser): Degasser(dp=0.149 bar, heat_transfer_coeff=1e+05)
  (filter_hot): Filter(dp_nominal=0.016 bar, m_dot_nominal=44.203 kg/s, clogging_dp=0.5 bar)
  (heat_exchanger): HeatExchanger(ua=1e+05 W/K, arrangement=counterflow, dp_hot_nominal=0 bar, dp_cold_nominal=0 bar)
  (filter_return): Filter(dp_nominal=0.016 bar, m_dot_nominal=44.203 kg/s, clogging_dp=0.5 bar)
  (injection_pump): InjectionPump(no_stages=10, efficiency=0.8, pump_type=DEFAULT-PUMP)
)
                                 energy_J  energy_MWh      peak_W  operating_hours  alarms  alarm_rate  skipped  errors
module            port
degasser                                0           0         NaN             4320       0           0        0       0
doublet.esp       electricity           0           0           0             4320   17280           1        0       0
doublet.injector  heat_loss   1.56973e+12     436.036      169242             4320       0           0        0       0
doublet.reservoir                       0           0         NaN             4320       0           0        0       0
filter_hot                              0           0         NaN             4320       0           0        0       0
filter_return                           0           0         NaN             4320       0           0        0       0
heat_exchanger                          0           0 3.93602e+06             4320       0           0        0       0
injection_pump    electricity 3.05408e+12     848.355      220543             4320       0           0        0       0
CalibrationResult(ua: 100000.0 -> 5317564.26321053; RMS 0.369074 -> 0.00307464; evaluations=16, success=True, applied=True)
                                 energy_J  energy_MWh      peak_W  operating_hours  alarms  alarm_rate  skipped  errors
module            port
degasser                                0           0         NaN               24       0           0        0       0
doublet.esp       electricity           0           0           0               24       0           0        0       0
doublet.injector  heat_loss   9.98057e+09     2.77238      115516               24       0           0        0       0
doublet.reservoir                       0           0         NaN               24       0           0        0       0
doublet.riser     heat_loss   1.77574e+10     4.93262      205526               24       0           0        0       0
doublet.sink                            0           0         NaN               24       0           0        0       0
doublet.well      heat_loss   9.53016e+10     26.4727 1.10303e+06               24       0           0        0       0
filter_hot                              0           0         NaN               24       0           0        0       0
filter_return                           0           0         NaN               24       0           0        0       0
heat_exchanger                          0           0 8.69861e+06               24       0           0        0       0
injection_pump    electricity 2.26485e+10     6.29125      262136               24       0           0        0       0

```

The whole-file HX fit is an API demonstration, not holdout validation. The reconciliation
fit below uses the first 672 observations only.

## 4. Replay timing and implementation costs

Final measured `Engine.replay`: **21.436 s for 17,280 rows**, zero errors and zero skips.

Timing starts after parsing the CSV and includes complete measured-twin calculations, health
and result collection. Environment: macOS, Python 3.11, existing `.venv311`; hardware model was not queried. Tests were
also active on the machine, so this is not an isolated hardware benchmark. An earlier run was
19.524 s. [Machine-readable timing](engine-timing.json).

The binding plan resolves equipment and units once and precomputes parameter-transition times.
Loader performs chunked reads, array indexing and vectorized missing-value masks instead of
per-row pandas lookup. Histories/bindings are fixed during a run; direct parameter overrides
remain supported. Immutable constant fluid properties were already cached and remain unchanged.
CSV-driver refreshes are keyed by file modification time/size; UTC timestamps are formatted after
removing their already-normalized timezone, avoiding costly repeated timezone formatting.
No physics equation, numeric precision or parameter reference value was changed for performance.

The suite intentionally executes the full acceptance calibration twice. Its final duration is
421.41 s; those two tests took 166.58 and 156.53 s, respectively. Ordinary engine/data/calibration
regressions run separately in about 31 s. No observations are subsampled in the acceptance fit.

## 5. Checkpoints, resume and idempotency

Trimmed real checkpoint specimen (ellipsis fields are explanatory):

```json
{
  "version": 1,
  "run_kind": "replay",
  "module_states": {},
  "clock": {
    "kind": "ticks",
    "ticks": [
      "2024-06-07T00:00:00+00:00",
      "...",
      "2024-12-03T23:45:00+00:00"
    ],
    "step": "0 days 00:15:00"
  },
  "position": "2024-12-03T23:45:00Z",
  "results_file": "replay.ckpt.results.cbc70cca4b00430481a29343024fed7e.parquet",
  "created_at": "2026-10-28T15:08:44.150778Z",
  "only": null,
  "on_error": "record",
  "plant": {
    "name": "geothermal_doublet",
    "plant_type": "geothermal_example",
    "modules": {
      "doublet.esp": {
        "type": "esp",
        "params": [
          {
            "valid_from": "2020-01-01T00:00:00Z",
            "params": {
              "no_stages": 15,
              "...": "..."
            }
          }
        ],
        "overrides": {},
        "active_from": "2020-01-01T00:00:00Z"
      }
    },
    "bindings": {
      "doublet.esp": {
        "inputs": {
          "frequency": {
            "column": "ESP_freq",
            "unit": "Hz"
          }
        },
        "streams": {
          "...": "..."
        },
        "measured": {
          "...": "..."
        },
        "state": {}
      }
    },
    "composites": {
      "...": "..."
    },
    "state": {
      "...": "..."
    },
    "boundary": {
      "...": "..."
    }
  },
  "dataset": {
    "kind": "csv",
    "path": ".../datasets/geothermal_doublet/geothermal_example_dataset.csv",
    "time_column": "Timestamp",
    "sep": null,
    "tz": "UTC",
    "units": {}
  }
}
```

The manifest contains full design, histories, bindings, composite metadata, current parameter
state/overrides, explicit dynamic module states, exact clock, completed position, source handle,
results reference, callback-independent run options and creation time. Results preserve lists,
booleans, nonfinite missing cells and full-precision floats with JSON-encoded cells in Parquet,
or CSV when Parquet is unavailable. Integration durations and diagnostics travel in metadata.

An immutable generation is written/flushed before atomic manifest replacement; old results
are removed only after successful publication. A generation suffix intentionally strengthens
the requested two-file pattern: replacing a fixed result file first could leave an old manifest
pointing at newer results. Interrupted failed writes can leave unreferenced generations.
One writer owns each checkpoint. File/remote source contents must stay stable for exact resume.

Verified:

- Replay and simulate interrupted after five completed ticks, saved in `on_error`, loaded in
  fresh Engine instances and resumed: frames and energy summaries match uninterrupted runs
  exactly; no completed tick repeats.
- Exhausted `resume()` returns the stored Results object; plant-only snapshots also restore.
- Measured state stays authoritative; unbound state integrates. Integrated state survives
  checkpoint/resume in a custom stateful module.
- AutoCheckpoint at a one-hour simulated interval saves four quarter-hour rows; resume adds
  only the fifth. Lifecycle callback order and committed position are checked.
- Three live calls at 01:00, 02:00 and 02:00 return **5, 4 and 0** new rows. The checkpoint
  contains nine unique rows. Empty live windows restore correctly.
- Injected manifest-rename failure leaves the previous generation readable; CSV fallback and
  exact cell/diagnostic round-trips pass.

Live returns only newly processed rows, while `engine.results` remains cumulative. The checkpoint
commits before sink delivery: external sinks need idempotent timestamp-based writes, and there is
no distributed exactly-once transaction with an external sink. Late rows behind the watermark
require an explicit replay. The engine never sleeps or schedules itself.

## 6. All end-to-end metrics versus the types phase

The values already present in [types-reconciliation.json](types-reconciliation.json) compare
**exactly equal**, including fitted UA, temperatures, energy residuals and alarm rates.
New per-output calibration diagnostics have no previous-task counterpart. Percentages below
are stored as fractions unless the name indicates K/W; consult column names for units.
[Full current JSON](engine-reconciliation.json).

| Metric | Types phase | Engine phase |
| --- | ---: | ---: |
| `rows` | 17280 | 17280 |
| `normal_rows` | 17280 | 17280 |
| `coverage.degasser` | 1 | 1 |
| `coverage.doublet.esp` | 1 | 1 |
| `coverage.filter_return` | 1 | 1 |
| `coverage.filter_hot` | 1 | 1 |
| `coverage.heat_exchanger` | 1 | 1 |
| `coverage.injection_pump` | 1 | 1 |
| `coverage.doublet.injector` | 1 | 1 |
| `coverage.doublet.reservoir` | 1 | 1 |
| `unmapped` | [] | [] |
| `ignored_count` | 119 | 119 |
| `median_relative_errors.doublet.esp.power` | 1 | 1 |
| `median_relative_errors.doublet.esp.head` | 0.63167758662 | 0.63167758662 |
| `median_relative_errors.filter_hot.pressure_drop` | 0.0169610215306 | 0.0169610215306 |
| `median_relative_errors.filter_return.pressure_drop` | 0.0169610215306 | 0.0169610215306 |
| `median_relative_errors.injection_pump.power` | 1.2319590001e-05 | 1.2319590001e-05 |
| `alarm_rates.degasser` | 0 | 0 |
| `alarm_rates.doublet.esp` | 1 | 1 |
| `alarm_rates.filter_return` | 0 | 0 |
| `alarm_rates.filter_hot` | 0 | 0 |
| `alarm_rates.heat_exchanger` | 0 | 0 |
| `alarm_rates.injection_pump` | 0 | 0 |
| `alarm_rates.doublet.injector` | 0 | 0 |
| `alarm_rates.doublet.reservoir` | 0 | 0 |
| `health_assessed.degasser` | False | False |
| `health_assessed.doublet.esp` | True | True |
| `health_assessed.filter_return` | True | True |
| `health_assessed.filter_hot` | True | True |
| `health_assessed.heat_exchanger` | True | True |
| `health_assessed.injection_pump` | False | False |
| `health_assessed.doublet.injector` | False | False |
| `health_assessed.doublet.reservoir` | False | False |
| `calibration.fitted.ua` | 7138598.61676 | 7138598.61676 |
| `calibration.rms_before` | 0.380431577909 | 0.380431577909 |
| `calibration.rms_after` | 0.000294183188779 | 0.000294183188779 |
| `calibration.observations` | 672 | 672 |
| `calibration.success` | True | True |
| `calibration.message` | `gtol` termination condition is satisfied. | `gtol` termination condition is satisfied. |
| `calibration.applied` | True | True |
| `calibration.initial.ua` | — | 100000 |
| `calibration.rms_by_output_before.cold_out_T` | — | 0.100811762344 |
| `calibration.rms_by_output_before.duty` | — | 0.638404112887 |
| `calibration.rms_by_output_before.hot_out_T` | — | 0.128303287695 |
| `calibration.rms_by_output_after.cold_out_T` | — | 7.74931227701e-05 |
| `calibration.rms_by_output_after.duty` | — | 0.000493777257312 |
| `calibration.rms_by_output_after.hot_out_T` | — | 9.90458568825e-05 |
| `calibration.evaluations` | — | 13 |
| `calibrated_hx_holdout_alarm_rate` | 0.832430154143 | 0.832430154143 |
| `electricity_twin_median_relative_error` | 0.387345431061 | 0.387345431061 |
| `wiring.edges` | 10 | 10 |
| `wiring.mismatches` | [] | [] |
| `electricity_chain_median_relative_error` | 0.297985586172 | 0.297985586172 |
| `holdout_and_chain.hx_hot_K.median` | 0.338789646623 | 0.338789646623 |
| `holdout_and_chain.hx_hot_K.max` | 0.566082421917 | 0.566082421917 |
| `holdout_and_chain.hx_cold_K.median` | 0.303712203579 | 0.303712203579 |
| `holdout_and_chain.hx_cold_K.max` | 0.488887537316 | 0.488887537316 |
| `holdout_and_chain.hx_duty.median` | 0.00629295147226 | 0.00629295147226 |
| `holdout_and_chain.hx_duty.max` | 0.0095232905132 | 0.0095232905132 |
| `holdout_and_chain.chain_wellhead.median` | 0.575904818721 | 0.575904818721 |
| `holdout_and_chain.chain_wellhead.max` | 0.580562067737 | 0.580562067737 |
| `holdout_and_chain.chain_hx_duty.median` | 0.124370110603 | 0.124370110603 |
| `holdout_and_chain.chain_hx_duty.max` | 0.143768214492 | 0.143768214492 |
| `balances.mass.max` | 0 | 0 |
| `balances.mass.median` | 0 | 0 |
| `balances.thermal.max` | 2.3628059904e-16 | 2.3628059904e-16 |
| `balances.thermal.median` | 4.37432335808e-17 | 4.37432335808e-17 |
| `balances.energy.max` | 0.00187310307765 | 0.00187310307765 |
| `balances.energy.median` | 0.00176456158752 | 0.00176456158752 |
| `balances.unresolved_W.max` | 230371.858219 | 230371.858219 |
| `balances.unresolved_W.median` | 212451.164665 | 212451.164665 |
| `balances.residual_W.max` | 230371.858219 | 230371.858219 |
| `balances.residual_W.median` | 212451.164665 | 212451.164665 |
| `balance_samples` | 100 | 100 |

All prior regression thresholds pass. This does not repair the existing physical limitations:
ESP head error remains 63.17%, power error 100%, ESP alarm rate 100%, held-out calibrated HX
alarm rate 83.24%, and total electrical error 38.73% on measured boundaries / 29.80% in the chain.
Mass and modeled thermal balance close; strict first-law closure still has the retained
isothermal-pump work residual. No alarms, losses or power were fabricated to hit old targets.

## 7. Calibration results

- HX, first seven days: UA **7,138,598.616760 W/K**; normalized RMS
  **0.380431577909 → 0.000294183188779**; 13 optimizer evaluations, 672 observations.
  Duty/hot/cold holdout errors remain exactly those in section 6.
- HX, complete acceptance CSV: UA **5,317,564.263211 W/K**; normalized RMS
  **0.369074 → 0.00307464**; 16 optimizer evaluations, successful default application.
- ESP head polynomial: synthetic 16-flow recovery test, 90–160 m³/h, target head 80% of
  the original model; normalized RMS **0.186364383937 → 1.43794664468e-15**, success,
  one optimizer evaluation after the linear polynomial initialization. `apply=False` leaves
  the supplied ESP untouched. This tests parameter recovery, not actual-project pump accuracy.

Fitted ESP coefficients (the original mixed US polynomial basis is retained):

```text
[100.41474080002418, -0.001668228480007171, 1.8316452080079156e-07, -1.1651217120041179e-11, 1.9028771600101154e-16, -9.46066848009295e-22]
```

[Full ESP fit diagnostics](engine-esp-calibration.json). All optimization predictions come from
public `Engine.replay(..., only=[module_path])`; residuals are normalized per measured output,
scalar/vector ParamRef bounds are respected, and one dated design snapshot is fitted at a time.
Successful `apply=True` persists explicit current overrides without adding a dated history entry.

## 8. New NOTE(refactor)s and other decisions

Two new source annotations describe boundary assumptions, not changes to physical equations:

1. Minimal two-control simulations use explicitly stored secondary defaults: 40 kg/s,
   20 °C, 5 bar, plus the existing 51.5-bar injection setpoint. Supplying bound columns
   replaces these assumptions. Measured replay always uses its measured equipment boundaries.
2. Root volumetric-to-mass conversion uses the project's fluid, matching the old scenario
   adapter's reservoir-density conversion. Exact scenario-reference parity verifies this.

Other decisions:

- `PlantConfig` remains the portable file format and import provenance; runtime execution
  reads module-owned bindings, boundaries, histories and overrides, never a config argument.
  Composite histories/current state are serialized as well as leaf equipment parameters.
- Schema-driven `extra_repr` supplies consistent human-unit formatting; key equipment uses
  `repr_fields` selections rather than duplicating formatting code in every class.
- The public top-level API stays exactly as requested. Advanced custom-module quantity/result
  contracts and callback extensions may import their dedicated core modules; common workflows
  need only `gm`. Existing fully explicit SI Profile construction remains supported.
- `Dataset.from_influx` takes an environment-variable name in `token`; AVEVA uses `secret_env`.
  This makes checkpoint descriptions reopenable without serializing credentials. Remote transport
  tests are mocked; the credential-dependent real AVEVA test is the sole skip.
- Mean sampling uses left-closed bins, numeric means and the final text flag; default execution
  uses previous sampling with bounded age. Timezone conversion preserves calendar DST durations.
- Checkpoints serialize data/state, never executable Python. Custom plant classes must be
  discoverable and implement their configuration factory. External scheduling, concurrent
  checkpoint writers, late-data backfill and transactional sink delivery are outside this loop.

## 9. Validation and local commits

```text
Baseline: 141 passed, 1 skipped in 49.20s
Final pytest tests: 160 passed, 1 skipped in 421.41s (0:07:01)
black --check gemini tests examples: 135 files would be left unchanged
isort --check-only gemini tests examples: clean
flake8 gemini tests examples: clean
git diff --check: clean
Original golden JSON and dataset files: unchanged
```

[Complete check output and durations](engine-checks.txt). A final presentation-only addition
makes both J and MWh visible in the printed summary; the acceptance output above exercises it.
Phase commits cover plant ownership, datasets/clocks, engine/checkpoints/calibration/API,
regression migration/examples, performance and documentation. No push or PR was performed.
