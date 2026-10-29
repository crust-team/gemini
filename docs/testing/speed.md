# Test-suite speed

Timings in this document were measured on the development machine with Python 3.12.10. The
repository supports Python 3.11 and 3.12; absolute CI times will differ, so compare changes on
the same runner.

## Before

Measured on 2026-10-28 from `refactor/legacy-in-core` (`3b100ed`) with:

```bash
PYTHONPATH=. .venv/bin/pytest --durations=50 -q
PYTHONPATH=. .venv/bin/pytest -m "not e2e" --durations=50 -q
```

The full suite was **152 passed in 609.40 s**. The non-e2e tier was **137 passed, 15
deselected in 15.39 s**.

### Full-suite slowest 50

| Seconds | Phase | Test |
| ---: | --- | --- |
| 195.73 | call | `e2e/test_quickstart.py::test_quickstart` |
| 186.71 | call | `e2e/test_module_api.py::test_module_api` |
| 103.35 | setup | `e2e/test_full_replay.py::test_complete_history_and_source_accounting` |
| 46.01 | call | replay example subprocess |
| 40.81 | call | `e2e/test_module_api_baseline.py::test_state_and_full_results_match_phase_zero` |
| 5.52 | call | legacy bridge example subprocess |
| 4.91 | call | calibration example subprocess |
| 3.78 | call | `e2e/test_legacy_bridge.py::test_legacy_bridge` |
| 2.33 | call | live example subprocess |
| 2.08 | call | simulate example subprocess |
| 1.41 | call | custom-plant example subprocess |
| 1.40 | call | inspect-plant example subprocess |
| 0.90 | call | `integration/test_engine.py::test_live_idempotency` |
| 0.89 | call | `integration/test_engine.py::test_interrupt_resume[simulate]` |
| 0.77 | call | `integration/test_calibrate.py::test_hx_apply_and_save` |
| 0.73 | call | `integration/test_engine.py::test_interrupt_resume[replay]` |
| 0.59 | call | `integration/test_calibrate.py::test_esp_head_coefficients` |
| 0.46 | call | `integration/test_engine.py::test_reference_replay_and_simulate` |
| 0.45 | call | `integration/test_engine.py::test_failed_checkpoint_publication_keeps_previous` |
| 0.44 | setup | `integration/test_engine.py::test_failed_checkpoint_publication_keeps_previous` |
| 0.42 | setup | `integration/test_engine.py::test_plant_only_checkpoint` |
| 0.42 | setup | `integration/test_engine.py::test_replay_can_skip_outputs` |
| 0.42 | setup | `integration/test_engine.py::test_reference_replay_and_simulate` |
| 0.40 | setup | `integration/test_engine.py::test_interrupt_resume[replay]` |
| 0.40 | setup | `integration/test_engine.py::test_missing_data_dates_events_and_export` |
| 0.39 | setup | `integration/test_engine.py::test_error_policies_and_missing_columns` |
| 0.39 | call | `integration/test_plant.py::test_handwritten_wiring_and_split_helpers` |
| 0.38 | setup | `integration/test_engine.py::test_autocheckpoint_and_callback_order` |
| 0.38 | setup | `integration/test_engine.py::test_live_idempotency` |
| 0.38 | setup | `integration/test_engine.py::test_interrupt_resume[simulate]` |
| 0.37 | setup | `integration/test_engine.py::test_empty_live_and_fallback_storage` |
| 0.35 | call | `integration/test_plant.py::test_trace_hooks_are_removed_after_failure` |
| 0.35 | call | `unit/test_forward_structure.py::test_registered_forward_structure` |
| 0.34 | call | `integration/test_engine.py::test_empty_live_and_fallback_storage` |
| 0.31 | call | `unit/test_forward_structure.py::test_fixed_signatures_and_declared_port_accesses` |
| 0.28 | call | `unit/test_forward_structure.py::test_leaf_and_composite_output_conventions` |
| 0.24 | call | `integration/test_engine.py::test_autocheckpoint_and_callback_order` |
| 0.24 | call | `unit/test_runtime.py::test_captured_monitoring_values` |
| 0.24 | call | `integration/test_engine.py::test_missing_data_dates_events_and_export` |
| 0.17 | call | `unit/core/modules/test_field_types.py::test_quantity_declarations_expose_units` |
| 0.16 | call | `unit/core/modules/heat/test_heatexchanger.py::test_measured_heat_exchanger_performance` |
| 0.14 | call | `integration/test_engine.py::test_plant_only_checkpoint` |
| 0.13 | call | `unit/test_public_api.py::test_readable_tree` |
| 0.11 | call | `unit/test_golden.py::test_golden` |
| 0.05 | call | `integration/test_engine.py::test_stateful_measured_and_integrated` |
| 0.04 | call | `unit/core/data/test_dataset.py::test_timezones_duplicates_profiles_and_validation` |
| 0.04 | call | `unit/core/modules/test_container.py::test_module_list_and_dict_registration` |
| 0.04 | call | `integration/test_engine.py::test_error_policies_and_missing_columns` |
| 0.03 | call | `unit/core/modules/test_module.py::test_formula_outputs_count_calls_sum_leaves_and_read_outlet_fields` |
| 0.03 | call | `unit/core/modules/test_module.py::test_output_records_are_nested_and_thread_local` |

### Non-e2e slowest 50

| Seconds | Phase | Test |
| ---: | --- | --- |
| 0.88 | call | `integration/test_engine.py::test_interrupt_resume[simulate]` |
| 0.86 | call | `integration/test_engine.py::test_live_idempotency` |
| 0.81 | call | `integration/test_calibrate.py::test_hx_apply_and_save` |
| 0.75 | call | `integration/test_engine.py::test_interrupt_resume[replay]` |
| 0.54 | call | `integration/test_calibrate.py::test_esp_head_coefficients` |
| 0.50 | call | `integration/test_engine.py::test_reference_replay_and_simulate` |
| 0.45 | call | `integration/test_engine.py::test_failed_checkpoint_publication_keeps_previous` |
| 0.43 | setup | `integration/test_engine.py::test_failed_checkpoint_publication_keeps_previous` |
| 0.39 | setup | `integration/test_engine.py::test_missing_data_dates_events_and_export` |
| 0.38 | setup | `integration/test_engine.py::test_interrupt_resume[replay]` |
| 0.38 | setup | `integration/test_engine.py::test_replay_can_skip_outputs` |
| 0.38 | setup | `integration/test_engine.py::test_autocheckpoint_and_callback_order` |
| 0.38 | call | `integration/test_plant.py::test_handwritten_wiring_and_split_helpers` |
| 0.37 | setup | `integration/test_engine.py::test_reference_replay_and_simulate` |
| 0.37 | setup | `integration/test_engine.py::test_plant_only_checkpoint` |
| 0.37 | setup | `integration/test_engine.py::test_error_policies_and_missing_columns` |
| 0.37 | setup | `integration/test_engine.py::test_interrupt_resume[simulate]` |
| 0.37 | setup | `integration/test_engine.py::test_empty_live_and_fallback_storage` |
| 0.37 | setup | `integration/test_engine.py::test_live_idempotency` |
| 0.35 | call | `integration/test_plant.py::test_trace_hooks_are_removed_after_failure` |
| 0.34 | call | `unit/test_forward_structure.py::test_fixed_signatures_and_declared_port_accesses` |
| 0.34 | call | `integration/test_engine.py::test_empty_live_and_fallback_storage` |
| 0.29 | call | `unit/test_forward_structure.py::test_registered_forward_structure` |
| 0.28 | call | `integration/test_engine.py::test_autocheckpoint_and_callback_order` |
| 0.28 | call | `unit/test_forward_structure.py::test_leaf_and_composite_output_conventions` |
| 0.23 | call | `integration/test_engine.py::test_missing_data_dates_events_and_export` |
| 0.16 | call | `unit/core/modules/test_field_types.py::test_quantity_declarations_expose_units` |
| 0.15 | call | `unit/core/modules/heat/test_heatexchanger.py::test_measured_heat_exchanger_performance` |
| 0.14 | call | `integration/test_engine.py::test_plant_only_checkpoint` |
| 0.13 | call | `unit/test_public_api.py::test_readable_tree` |
| 0.13 | call | `unit/test_runtime.py::test_captured_monitoring_values` |
| 0.11 | call | `unit/test_golden.py::test_golden` |
| 0.08 | call | `unit/core/modules/test_module.py::test_call_output_and_signature_guards` |
| 0.04 | call | `integration/test_engine.py::test_stateful_measured_and_integrated` |
| 0.04 | call | `unit/core/data/test_dataset.py::test_timezones_duplicates_profiles_and_validation` |
| 0.04 | call | `unit/core/modules/test_container.py::test_module_list_and_dict_registration` |
| 0.04 | call | `integration/test_engine.py::test_error_policies_and_missing_columns` |
| 0.03 | call | `unit/core/modules/test_module.py::test_formula_outputs_count_calls_sum_leaves_and_read_outlet_fields` |
| 0.03 | call | `unit/core/modules/test_module.py::test_output_records_are_nested_and_thread_local` |
| 0.02 | call | `unit/core/modules/pumps/test_esp.py::test_fit_recovers_curve_and_health_threshold` |
| 0.02 | call | `unit/core/types/test_cost.py::test_cost_aggregation` |
| 0.02 | call | `integration/test_engine.py::test_replay_can_skip_outputs` |
| 0.02 | call | `unit/core/types/test_declarations.py::test_parameter_units_shape_and_metadata` |
| 0.02 | call | `unit/core/modules/heat/test_heatexchanger.py::test_first_law_equal_capacity_and_limits[counterflow]` |
| 0.02 | call | `unit/core/modules/heat/test_heatexchanger.py::test_first_law_equal_capacity_and_limits[parallel]` |
| 0.02 | call | `unit/core/types/test_profile.py::test_profiles_drive_scenario` |
| 0.01 | call | `unit/core/modules/test_module.py::test_outlet_dict_names_and_flow_types_are_checked` |
| 0.01 | call | `unit/core/modules/test_balance.py::test_esp_motor_efficiency_does_not_change_shaft_power` |
| 0.01 | call | `unit/core/modules/pumps/test_esp.py::test_original_nonzero_power_reference` |
| 0.01 | call | `unit/core/engine/test_registry.py::test_known_modules_are_registered_and_grouped` |

No non-e2e test exceeded one second.

### Profiles of the five slowest tests

Profiles were captured with `python -m cProfile -o /tmp/<name>.prof -m pytest <nodeid>` and
read with `pstats`, sorted by cumulative time.

| Test | Profiled time | Dominant work |
| --- | ---: | --- |
| quickstart | 384.93 s | 360.37 s in 24 engine runs; 284.44 s in calibration; 363,072 twin steps |
| module API | 368.76 s | 361.96 s in 21 replays; 286.25 s in calibration; 362,880 twin steps |
| full replay | 223.29 s | 118.87 s chained simulation, 98.69 s replay; 17,280 chained steps |
| replay example | 42.38 s | 42.30 s waiting for the subprocess, whose script performs full-year replay |
| baseline parity | 79.73 s | 75.81 s replay; 17,280 twin steps and 138,240 module calls |

`cProfile` tracing roughly doubled engine-heavy timings. The baseline parity profile completed
the replay but its internal unprofiled-runtime guard then failed at 76.49 s (`<60 s` required),
before simulation; the ordinary baseline run passed at 40.81 s. Across profiles, elapsed time
is driven by the number of engine steps, module calls, validation, and repeated optimizer
residual replays. CSV loading and legacy conversion are not dominant, and no repeated pure
fluid-property function justifies a production cache.

## Slow-dataset golden confirmation

Before adding fast-data fixtures, the unchanged full-year dataset passed all 152 tests and the
existing replay/simulate goldens in **609.40 s**. The source
`examples/shared/doublet_heat/doublet_2024_15min.csv` remains unchanged.

The fast dataset is July 2024: the first complete calendar month after the source begins on
June 7. Its 2,976 contiguous 15-minute rows retain ordinary control variation, day boundaries,
checkpoint cadence, calibration/holdout windows, measured replay, full-chain simulation and
live updates without making a partial month the long-term fixture. Generate the byte-for-byte
source slice and unchanged-code replay golden with:

```bash
PYTHONPATH=. python tests/fixtures/generate_fast_fixtures.py
```

The generated files are
`examples/shared/doublet_heat/doublet_2024_15min_month.csv` and
`tests/fixtures/module_api_fast/replay.csv.gz`. Never replace or shrink the full-year dataset or
its existing goldens. `--dataset=fast` selects July by default; `--dataset=slow` selects the
untouched full dataset.

## After

Measured on 2026-10-29 after all phases:

| Selection | Before | After |
| --- | ---: | ---: |
| default fast tier, serial | 15.39 s | **9.18 s** |
| default fast tier, `-n auto` | unavailable (xdist not installed) | **7.60 s** |
| all 152 tests, fast data, serial | unavailable | **116.44 s** |
| all 152 tests, fast data, `-n auto` | unavailable | **82.95 s** |
| all 152 tests, full-year data, serial | 609.40 s | **621.30 s** |
| all 152 tests, full-year data, `-n auto` | unavailable | **506.23 s** |

The slow serial variation confirms the full-year workload was preserved rather than optimized by
changing results. The feature/default paths are faster because they select the July fixture and
share immutable setup; the full-year CI improvement comes from xdist. In the duration run, the
default tier's slowest call was 0.60 s, below the enforced one-second budget.

### Ten biggest wins

| Test or fixture | Before | After | Change |
| --- | ---: | ---: | --- |
| quickstart | 195.73 s | 37.58 s | selected July while retaining every public workflow |
| module API | 186.71 s | 23.41 s | selected July for replay and optimizer evaluations |
| full-replay verification fixture | 103.35 s | 19.02 s | selected July; still replay/calibrate/holdout/simulate |
| replay example subprocess | 46.01 s | 8.09 s | example test passes selected July path through the environment |
| baseline replay parity | 40.81 s | 10.96 s | compares against the generated unchanged-code July golden |
| default fast tier | 15.39 s | 9.18 s | session datasets/plant plus cheap isolated plant copies |
| live idempotency | 0.90 s | 0.07 s | minimal stateful plant and two ticks preserve checkpoint semantics |
| interrupt/resume simulation | 0.89 s | 0.38 s | 12-step window still crosses the interruption boundary |
| interrupt/resume replay | 0.73 s | 0.34 s | same shorter exact-resume window |
| repeated plant/data setup | 0.35–0.44 s/test | 0.23 s once | session load; mutating tests use `deepcopy` |

No test was moved to `slow`; the existing 15 e2e cases remain e2e. No production cache was
added because profiles showed engine-step/module-validation volume, not repeated pure fluid or
correlation calls, dominated runtime.
