# Testing

Tests have four roles:

- `tests/unit/` mirrors every source file with logic.
- `tests/integration/` combines plants, data, engines, callbacks, checkpoints, and calibration.
- `tests/e2e/` runs public workflows and committed real example data; tests use `@pytest.mark.e2e`.
- `tests/fixtures/` contains immutable golden values and captured pre-refactor engine frames.

`tests/unit/test_mirror.py` enforces the source mirror rule; `__init__.py` and pure re-export
files are excluded. Only `tests/unit/core/legacy/` and `tests/e2e/test_legacy_bridge.py` read old
formats. E2E tests cover the literal quickstart, 17,280-row reconciliation, calibration holdout,
mass/thermal balance, electricity limitations, alarm rates, bridge round trips, example
subprocesses, live idempotency, and exact interrupt/resume results.

```bash
python -m pytest -m "not e2e"
python -m pytest
black --check gemini tests examples
isort --check-only gemini tests examples
flake8 gemini tests examples
```
