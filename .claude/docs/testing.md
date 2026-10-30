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
5. any other changed file selects the tests (or `conftest.py` scopes) whose source names its path.

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
(`uv pip install --resolution lowest-direct -e ".[parquet]" --group test`), which proves the
ranges. Free-threaded 3.14t and the 3.15 beta run with `continue-on-error`, so their failures are
reported without failing the build. Locally, `uv venv -p 3.11` and the same install reproduce
any job. Raise a lower bound in `pyproject.toml` when code needs a newer API, and add an upper
bound only for a known incompatibility.

## Speed budget and slow tests

An individual fast-tier test call may take at most one second. In the development profile the
root `tests/conftest.py` hook fails a slower unit or integration test, also inside xdist workers,
with instructions to optimize it or mark it `slow`. E2E tests, including the example smoke
tests, are exempt, and the release profile does not enforce the budget.
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
ESP over the July dataset tick by tick and as one traced NumPy call and checks they agree.

## Shared fixtures

Read-only expensive setup belongs in session or module fixtures. `dataset_path`,
`selected_frame` and `selected_dataset` load the chosen e2e data once; `fast_frame`,
`fast_dataset` and `reference_dataset` serve short behaviour checks; `shared_plant` validates
`plant.json` once; a test that takes `module_class` runs once per shipped module class and
example plant (`pytest_generate_tests` in `tests/conftest.py`), so each class stays within the
per-test budget. Never mutate these objects. Request `fresh_plant` for a function-scoped deep
copy or `module_plant` when one workflow shares a copied plant across assertions. Prefer the
shortest `Dataset.window` that still crosses every boundary relevant to the property.

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
`tests/unit/test_package_boundaries.py` checks that `gemini.utils` and `gemini.errors` import
nothing else from `gemini`. `tests/unit/test_code_quality.py` enforces the comment rule, the
nesting limit, the function-length limit with its `LONG_FUNCTIONS` exceptions and the ban on the
framework name (see [conventions.md](conventions.md#code-quality)); flake8 enforces complexity.
`tests/unit/test_public_api.py` pins the curated `gm` names and the version.

## Old formats, examples and e2e coverage

Old-format files are read only by `tests/unit/core/legacy/`, `tests/e2e/test_legacy_bridge.py`,
the `check_wiring` audit in `tests/e2e/test_full_replay.py`, and the golden reconstructions that
build equipment from the original `.param` files: the subsurface and heat-exchanger unit tests,
`tests/unit/core/physics/test_geometry.py`, `tests/integration/test_plant.py` and the historical
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
