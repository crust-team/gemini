# Core physics rules

`gemini/core/physics` contains reusable correlations: conversions, constants, fluids, geometry,
hydraulics, heat transfer, pumps, chemistry, corrosion and erosion.

- Use plain typed functions and SI inputs/outputs; small structured return models are allowed.
- State dimensions, reference formulas and assumptions in docstrings.
- Keep correlation-specific US or laboratory bases explicit at the formula boundary.
- Do not perform database I/O, logging or mutate global state during calculations.
- Fluid dtype instances own immutable overrides; cached property factories live in core.types.
  Physics must not import types at runtime.
- Do not hide undefined diagnostics as valid numbers. The receiving aquifer's unconfigured
  drainage radius leaves radial estimates unavailable while its pressure-flow model works.
- Preserve original numerical cases in `tests/golden`. Intentional changes require a
  `NOTE(refactor)` and measured or physical evidence; see `refactor-notes.md`.
