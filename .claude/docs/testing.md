# Testing

Always test what changed and everything that imports it; never run the full suite locally.

Every test belongs to one automatically marked folder tier:

- `tests/unit/` mirrors source files and receives `unit`.
- `tests/integration/` combines runtime components and receives `integration`.
- `tests/e2e/` runs complete public workflows on committed real data and receives `e2e`.
- `tests/fixtures/` contains immutable captured values, generators and golden outputs.

The registered markers are `unit`, `integration`, `e2e` and `slow`, with strict marker checking.
Default options (`addopts` in `pyproject.toml`) run in parallel with `-n auto --dist loadgroup`
and select `not e2e and not slow`; the profiles below choose their own markers. Use `make test`,
`make test-release` and `make lint` (flake8, black and isort over `gemini`, `tests`, `examples`,
`scripts` and `docs/conf.py`, as in the Lint workflow) rather than assembling commands by hand.

## Test profiles

Both profiles always run in parallel with `pytest-xdist`.

**Development** is the default for local work, every task and every commit:

```bash
make test                                    # same as: python scripts/test_changed.py
python scripts/test_changed.py --dry-run     # print the selection and the reasons
python scripts/test_changed.py --base origin/main -- -x
```

`scripts/test_changed.py` takes the files changed against `HEAD` (plus uncommitted and untracked
files, plus commits since `--base <ref>`), builds the `ast` import graph of `gemini/`,
`examples/`, `tests/` and `scripts/` (cached in `.tmp/test_changed/`), and selects the tests of the
changed files and of every module that imports a changed module, directly or transitively:

1. a changed test file runs itself; a changed `conftest.py` runs every test below it;
2. `pyproject.toml`, `tests/conftest.py` and `tests/xdist_plugin.py` select every test;
3. every affected `gemini/<path>/<name>.py` runs `tests/unit/<path>/test_<name>.py`, and every
   affected test file runs; imports made by `conftest.py` files are not followed;
4. a changed numbered example selects `tests/e2e/test_examples.py`;
5. any other changed file selects the tests (or `conftest.py` scopes) whose source names its path;
6. `tests/unit/test_code_quality.py` always runs, whatever changed and also when nothing else is
   selected, and its reason is printed.

It prints what it chose and why, then runs `pytest -n auto -m "not slow" --dataset=fast
--profile=development` on the selection. Tests marked `slow` belong to the release profile.
The development budget is **300 s** wall time: a session-end guard in `tests/conftest.py` fails a
development-profile run over 300 s and prints the 10 slowest test phases. An individual fast-tier
test call may take at most one second (below).

**Release** runs in CI before merging to `main` and for release tags:

```bash
make test-release      # pytest -n auto -m "" --dataset=slow --profile=release --durations=20
```

It runs every tier on the slow full-year dataset with no time budget; CI reports its durations.
Pull requests and feature-branch pushes run the development profile against their base
(`scripts/test_changed.py --base origin/<base>`). Pushes to `main`, release tags, pull requests
targeting `main` and merge queues run the release profile and must pass; a manual run of the Test
workflow (`workflow_dispatch`) runs the release profile on any branch.

## Python versions and dependency ranges

The Test workflow runs its profile on every supported Python, 3.11 to 3.14, with the newest
dependencies, and on 3.11 and 3.14 with the lowest versions `pyproject.toml` declares
(`uv pip install --resolution lowest-direct -e . --group test`), which proves the
ranges. Free-threaded 3.14t and the 3.15 beta run with `continue-on-error`, so their failures are
reported without failing the build. Locally, `uv venv -p 3.11` and the same install reproduce
any job. Raise a lower bound in `pyproject.toml` when code needs a newer API, and add an upper
bound only for a known incompatibility.

## Speed budget and slow tests

An individual fast-tier test call may take at most one second **of CPU time**. In the
development profile the root `tests/conftest.py` hook fails a unit or integration test whose call
phase (without fixture setup and teardown) used more, also inside xdist workers, with
instructions to optimize it or mark it `slow`. E2E tests, including the example smoke tests, are
exempt, and the release profile does not enforce the budget.

The measure is `time.process_time()` around the call (`tests/cpu_budget.py`), not elapsed time:
under `-n auto` or on a busy machine a test is descheduled and its wall time grows without any
extra work, so a wall-clock budget flaked on tests that need 0.5 s alone. `process_time` adds the
CPU of every thread of the process, so work a test hands to its own threads or to the NumPy
thread pool still counts (`thread_time` would miss it and let a heavy test pass), while sleeping
and waiting do not count. A worker runs one test at a time, so the process clock belongs to the
test. The budget stays one second; the failure message shows CPU and elapsed time. Never raise
the budget, skip a test or mark it flaky to get under it.

CPU time is much steadier than elapsed time but not immune to load: on an oversubscribed
machine (load average several times the core count) the same work can use up to about 2.5 times
the CPU seconds, because threads land on slower cores and share caches. A test that needs 0.4 s
alone can then read 1.0 s. Keep tests well under half a second of CPU time alone, and rerun a
borderline failure on a quiet machine before believing it.

To see how close tests are, run `--durations=10` (wall time, serial with `-n 0` for stable
numbers). Parse-heavy checks cache per process: `functions(path)` in
`tests/unit/test_code_quality.py` parses each file once, and the long-function exception check
parses only the files that hold an exception.
Marking is allowed only when the property inherently needs long elapsed work or a large real-data
window; add a one-line reason to its docstring. Do not delete, skip or weaken a test to meet the
budget.

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

Regenerate the July slice (byte-for-byte) and the unchanged-code replay golden with:

```bash
PYTHONPATH=. python tests/fixtures/generate_fast_fixtures.py
```

The generator fixes gzip metadata for reproducible output. The replay golden reproduces within
the documented `REPLAY_RTOL` (one binary64 ULP), not byte for byte: the committed file was
captured in another numeric environment. Under pandas 3 the comparison uses `PARSER_RTOL`
(2e-13) instead, because pandas 3 parses the CSV decimals correctly rounded where pandas 2 did
not (see [refactor-notes.md](refactor-notes.md#dependency-upgrades)); never regenerate the golden
to absorb a parser difference. Review generated diffs and run e2e
on both datasets before accepting a golden change. Golden changes are evidence of a numerical
change and are never a routine speed optimization.

Benchmarks are scripts, not tests: `PYTHONPATH=. python scripts/benchmark_esp.py` times the
ESP over the July dataset tick by tick and as one traced NumPy call, with and without
common-subexpression elimination, and the full `doublet_heat` replay on the old path and through
the graph, and checks that they agree.

## Shared fixtures

Read-only expensive setup belongs in session or module fixtures. `dataset_path`,
`selected_frame` and `selected_dataset` load the chosen e2e data once; `fast_frame`,
`fast_dataset` and `reference_dataset` serve short behaviour checks; `shared_plant` validates
`plant.json` once; a test that takes `module_class` runs once per shipped module class and
example plant (`pytest_generate_tests` in `tests/conftest.py`), so each class stays within the
per-test budget. Never mutate these objects. Request `fresh_plant` for a function-scoped deep
copy or `module_plant` when one workflow shares a copied plant across assertions. Prefer the
shortest `Dataset.window` that still crosses every boundary relevant to the property.

`tests/fixtures/equivalence.py` compares the paths of one source within `RTOL` (1e-12, defined in
`tests/fixtures/parity.py`): `assert_function_matches` a physics function on floats against arrays,
`assert_same_error` its failing row, and `assert_module_matches` a module called per row against
the graph run on every backend. Every physics function and module has such a test, over rows that
cross every branch. A module with no inlets, and a stateful module's `_advance_states`, are tested
on arrays directly. A module with a list output (the wells' section profiles) compares each item.

## Backend parity

`BACKENDS = ("python", "numpy")` in `tests/fixtures/parity.py` is the one list of backends under
test; the first is the reference, every other one is compared with it, and no test names a
backend. **Adding a backend means adding its name to `BACKENDS`** (after registering it in
`gemini.backends`); nothing else changes, and every test below then runs on it.

- **Modules.** `assert_module_matches` runs the graph on every backend, forced around the whole
  call (tracing included), compares each with the eager calls and each with the reference, so every
  per-module test is a parity test. `test_every_shipped_leaf_module_has_a_parity_test` in
  `tests/integration/test_backend_parity.py` lists the shipped stateless leaf classes and checks
  that the mirrored test file calls `assert_module_matches`. Stateful leaves go through the engine
  cases.
- **Whole runs** (fast tier, a window of 24 to 48 rows, `run_engine` and `assert_runs_match`).
  A `Snapshot` holds the frame and dtypes, skips, errors (class, message, module, tick), summary,
  persisted inputs, module states, graph breaks, every callback hook with the `ModuleResult` tree
  of each tick (`engine.step_results`: outputs, outlets, inlets, inputs, children, their Python
  types), the `EventLog` events without timestamps and the error that ended the run. The tests
  cover replay, faulted rows, `on_error="raise"`, stateful and composite twins, simulate (clean and
  faulted), live, `EventLog`, `AutoCheckpoint` with resume, health columns, output types and
  column dtypes. Floats compare within `RTOL`; structure and types compare exactly.
- **Examples** (`tests/e2e/test_backend_parity.py`, `slow`). Each numbered example runs under every
  backend through `tests/fixtures/run_example.py`, which reads `GEMINI_EXAMPLE_BACKEND`, enters
  `gemini.backends.settings` and runs the script with `runpy`; standard output without timing
  lines must be equal.

The engine itself is also compared on both backends with synthetic twins in
`tests/unit/engine/test_runner.py` (modules in `tests/fixtures/engine_plants.py`) and on the
doublet heat plant in `tests/integration/test_replay_graph.py`.

## Parallel-test rules

The suite must remain safe under `pytest -n auto`:

- write only below `tmp_path` or `tmp_path_factory` locations;
- never use a shared generated filename or mutate a committed fixture;
- restore monkeypatches, hooks, context variables and runtime settings;
- do not rely on test order or process-global state;
- deep-copy mutable plants instead of changing session fixtures.

## Structure and quality tests

`tests/unit/test_mirror.py` enforces source mirroring: every `gemini/<path>/<name>.py` except
`__init__.py`, including `gemini/utils/` and `gemini/errors/`, has a mirrored
`tests/unit/<path>/test_<name>.py` that defines at least one test. Its `PLACEHOLDERS` set of
mirrors still holding only a docstring is empty and must never grow.
`tests/unit/test_package_boundaries.py` checks that `gemini.errors` and the topic files of
`gemini.utils` import nothing else from `gemini`, and that `gemini.utils.data` imports no module
or engine code and `gemini.utils.legacy` no engine code. `tests/unit/test_code_quality.py` enforces the comment rule, the
nesting limit, the function-length limit with its `LONG_FUNCTIONS` exceptions and the ban on the
framework name (see [conventions.md](conventions.md#code-quality)); flake8 enforces complexity.
The same file fails on a formula in a module and on two physics functions with one normalised body;
`tests/unit/modules/test_glossary.py` checks every declared name against the glossary.
`tests/unit/test_public_api.py` compares every public name, its parameter names and the schema
files with `tests/fixtures/public_api.json`, which may only change together with `gm.API_VERSION`
(see [conventions.md](conventions.md#public-api-freeze)).
`tests/integration/test_public_contracts.py` checks that every public function that returns data
gives plain JSON on the example plant, and `tests/unit/scripts/test_write_schemas.py` that the
files of `docs/schemas/` are up to date and each sample fits its schema, with the small checker
in `tests/fixtures/json_schema.py`.

## Old formats, examples and e2e coverage

Old-format files are read only by `tests/unit/utils/legacy/`, `tests/e2e/test_legacy_bridge.py`,
the `check_wiring` audit in `tests/e2e/test_full_replay.py`, and the golden reconstructions that
build equipment from the original `.param` files: the subsurface, wells and exchangers unit tests,
`tests/unit/physics/test_geometry.py`, `tests/integration/test_plant.py` and the historical
`tests/fixtures/capture_golden.py`. Shared paths live in `tests/fixtures/__init__.py` (`ROOT`,
`FIXTURES`, `SHARED`, `OLD_PROJECT`).

The example smoke tests are the e2e cases of `tests/e2e/test_examples.py`, one per numbered
example. They run in both profiles (the development profile selects them when a numbered
example changes) and are exempt from the one-second budget; a 900 s hang guard (`TIMEOUT_S`)
stops a stuck one. Each example runs as a subprocess in `tmp_path` with an `examples` symlink, so
its output never lands in the repository;
`GEMINI_EXAMPLE_DATASET` points the examples that read the shared CSV at the selected dataset.
Expensive module-scoped e2e fixtures carry `pytest.mark.xdist_group`; the default
`--dist loadgroup` runs each group on one worker so the fixture is built once. E2E retains the
quickstart acceptance path (`tests/e2e/test_quickstart.py`), reconciliation, calibration
holdout, balances/electricity limits, alarm rates, bridge round trips, example subprocesses, live
idempotency and exact interrupt/resume coverage.
