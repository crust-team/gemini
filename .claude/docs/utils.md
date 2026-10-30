# Utilities

`gemini/utils/` holds general-purpose helpers that know nothing about geothermal physics, modules
or the engine. It is a leaf package: it imports only the standard library and installed
dependencies, never another part of `gemini` (`tests/unit/test_package_boundaries.py` enforces
this). It therefore cannot raise `gm.errors` classes; its helpers raise built-in exceptions such
as `TypeError` and `ValueError`, and callers that need a GEMINI error convert them. Import helpers
from their topic module, for example `from gemini.utils.strings import did_you_mean`;
`gemini/utils/__init__.py` exports nothing.

- `strings.py`: `snake_case`, `first_paragraph`, `join_path`, `split_path`, `join_names`,
  `did_you_mean`.
- `time.py`: `to_utc`, `to_utc_index`, `parse_duration`, `median_step`, `interval_seconds`,
  `DEFAULT_STEP`.
- `hooks.py`: `RemovableHandle` (ordered hook dicts, safe double `remove()`), `has_signature`, `observer` and `is_observer` (the read-only mark of a hook).
- `mappings.py`: `AttributeMapping` (base of `Ports` and `Values`), `get_nested`, `set_nested`.
- `context.py`: `ContextSetting`, a context variable change usable as `with` and as a decorator.
- `files.py`: `read_json`, `write_json` and the lossless JSON-cell tables (`encode_cell`,
  `encode_cells`, `decode_cells`) used by checkpoints and results.
- `collect_env.py`: `python -m gemini.utils.collect_env` prints the versions a bug report needs.

## Adding a helper

Add a helper only when at least two places need it, or when it removes a duplicate. Put it in the
file of its topic (no `misc.py` or `helpers.py`), give it a docstring, replace every duplicate in
the same commit and add a test to the mirrored `tests/unit/utils/test_<file>.py`. A new topic file
needs its own mirror, which `tests/unit/test_mirror.py` requires. Physics, units and quantities
belong in `core/physics` and `core/types`; code that needs modules or the engine stays in those
packages.
