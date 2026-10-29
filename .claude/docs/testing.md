# Testing

`pytest` is the day-to-day fast tier and must finish in under 30 seconds. Every test belongs to
one automatically marked folder tier:

- `tests/unit/` mirrors source files and receives `unit`.
- `tests/integration/` combines runtime components and receives `integration`.
- `tests/e2e/` runs complete public workflows on committed real data and receives `e2e`.
- `tests/fixtures/` contains immutable captured values, generators and golden outputs.

The registered markers are `unit`, `integration`, `e2e` and `slow`, with strict marker checking.
Default options select `not e2e and not slow`. Run from the repository root:

```bash
pytest                                      # fast unit + integration tier
pytest -n auto                              # parallel fast tier
pytest -m "e2e or slow" --dataset=fast     # slow tier on July data
pytest -n auto -m "" --dataset=fast         # every test, fast data
pytest -n auto -m "" --dataset=slow         # every test, full-year merge gate
```

An empty `-m ""` overrides the default selection. CI runs parallel fast and fast-data e2e jobs
for feature work. Main pushes, pull requests targeting main and merge queues run every test with
`--dataset=slow` as the merge gate.

## Speed budget and slow tests

An individual fast-tier test call may take at most one second. During the serial default fast
selection, the root `tests/conftest.py` hook fails a slower test with instructions to optimize it
or mark it `slow`. It is not enforced in xdist workers or during all-tier runs, where concurrent
load would distort a test's timing. Marking is allowed only when the property inherently needs
long elapsed work or a large real-data window; add a one-line reason to its docstring. Do not
delete, skip or weaken a test to meet the budget. Timing history and profiles live in
[docs/testing/speed.md](../../docs/testing/speed.md).

## Fast and slow datasets

`--dataset=fast` selects the committed 2,976-row July 2024 calendar month at
`examples/shared/doublet_heat/doublet_2024_15min_month.csv`. July is the first complete month
after the source begins on June 7 and retains 15-minute cadence, daily boundaries, calibration
and holdout periods, replay, simulation, checkpoints and live paths. Behaviour tests use short
windows, normally one point to seven days. The shared `fast_dataset` fixture is independent of
the e2e option. The 96-row `reference_dataset` is the narrow June window required by immutable
pre-refactor engine-frame goldens.

`--dataset=slow` selects the unchanged 17,280-row source at
`examples/shared/doublet_heat/doublet_2024_15min.csv`. Never delete, replace or shrink either
dataset or any golden. Full-year replay/simulate goldens remain under
`tests/fixtures/module_api_baseline/`; the fast replay golden is under
`tests/fixtures/module_api_fast/`.

Regenerate the July byte-for-byte slice and unchanged-code replay golden with:

```bash
PYTHONPATH=. python tests/fixtures/generate_fast_fixtures.py
```

The generator fixes gzip metadata for reproducible output. Review generated diffs and run e2e
on both datasets before accepting a golden change. Golden changes are evidence of a numerical
change and are never a routine speed optimization.

## Shared fixtures

Read-only expensive setup belongs in session or module fixtures. `selected_frame` and
`selected_dataset` load chosen e2e data once; `fast_frame`, `fast_dataset` and
`reference_dataset` serve short behaviour checks; `shared_plant` validates `plant.json` once.
Never mutate these objects. Request `fresh_plant` for a function-scoped deep copy or
`module_plant` when one workflow shares a copied plant across assertions. Prefer the shortest
`Dataset.window` that still crosses every boundary relevant to the property.

## Parallel-test rules

The suite must remain safe under `pytest -n auto`:

- write only below `tmp_path` or `tmp_path_factory` locations;
- never use a shared generated filename or mutate a committed fixture;
- restore monkeypatches, hooks, context variables and runtime settings;
- do not rely on test order or process-global state;
- deep-copy mutable plants instead of changing session fixtures.

`tests/unit/test_mirror.py` enforces source mirroring. Only `tests/unit/core/legacy/` and
`tests/e2e/test_legacy_bridge.py` read old formats. E2E retains the literal quickstart,
reconciliation, calibration holdout, balances/electricity limits, alarm rates, bridge round
trips, example subprocesses, live idempotency and exact interrupt/resume coverage.
