# Runtime settings

`gm.runtime` contains process defaults that should not be design parameters:

- `set_default_fluid` / `get_default_fluid`
- `set_precision("float64" | "float32")` / `get_precision`
- `set_display_units("si" | "field")` / `get_display_units`
- `manual_seed(seed)`
- `state()` / `load_state(mapping)`

Use `with gm.runtime.settings(precision="float32", display_units="field"):` for temporary
changes. Settings use `contextvars`, so nested scopes, threads and worker tasks restore their own
state safely. Precision controls correlations that need legacy float32 parity. Display units
affect representations only. A default fluid is copied into newly built modules and streams;
explicit fluids always win. Checkpoints retain and restore the runtime state used by a run.
