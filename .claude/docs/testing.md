# Testing

Mirror implementation paths under `tests/core`. Test behaviour, physical limits and failure
handling. Equipment tests cover validated parameters, port contracts, fidelity, mass/energy
balance, reference numbers and health thresholds. Module tests cover child paths, recursive
parameters, atomic JSON state loading, hook order/removal and stateful composition. Handwritten-plant tests verify actual stream identity wiring, hook cleanup and the buried ESP split.
Types tests cover quantity bounds, recursive numeric schemas, Fluid caching/composition, profiles
and compatible cost aggregation. Balance tests distinguish thermal closure from unresolved work.

`tests/golden/golden_values.json` and `runtime_values.json` are immutable. The historical
capture script is archival; do not regenerate expected values from the replacement API.
Monitoring parity is reconstructed in golden tests using public physics, never production
compatibility adapters.

`tests/e2e/test_geothermal_example.py` runs by default despite its `slow` marker. It loads the
project and saved JSON, replays all 17,280 rows, checks coverage and finite soft sensors, fits
HX conductance on the first 672 observations and evaluates the remaining 16,608 observations.
It also runs a handwritten plant for every row. Explicit `NOTE(refactor)` comments explain
source-model inconsistencies and changed accuracy limits. These are reported limitations,
not evidence that the original accuracy targets were achieved.

All ten examples are executed by `tests/test_examples.py`. External AVEVA tests skip only
without credentials. Install the optional `parquet` extra to exercise that export check.

```bash
poetry run black --check gemini tests examples
poetry run isort --check-only gemini tests examples
poetry run flake8 gemini tests examples
poetry run pytest tests
```
