# Testing

- Tests mirror the package: `tests/core/physics/test_hydraulics.py`,
  `tests/components/pumps/test_esp.py`.
- Test behaviour, physical limits and failure handling. Do not add tests that only repeat the
  implementation.
- Every component has tests for: parameter validation (valid example, missing field, wrong type,
  out-of-range value), port contract, `schema()` serialisation, reference numbers, and `health`
  thresholds when implemented.
- Reference numbers come from a documented source: golden values captured from the original
  GEMINI models (`tests/golden/golden_values.json`), a textbook example, or measured data in
  `datasets/`. Write the source next to the expected value.
- Physics functions get at least one energy- or mass-balance or limiting-case check (zero flow,
  equal temperatures, infinite UA).
- Tests that need external services (InfluxDB, AVEVA) are skipped when credentials are missing.
- Examples in `examples/` are run by `tests/test_examples.py`.

Validation commands:

```bash
poetry run black --check gemini tests
poetry run isort --check-only gemini tests
poetry run flake8 gemini tests
poetry run pytest tests
```
