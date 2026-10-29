# Core physics rules

`gemini/core/physics` contains reusable correlations: unit conversions, constants, fluid
properties, geometry, hydraulics, heat transfer, pumps, chemistry, corrosion and erosion.

- Use plain typed functions and SI inputs/outputs; small structured return models are allowed.
- State dimensions, reference formulas and assumptions in docstrings.
- Keep correlation-specific US or laboratory bases explicit at the formula boundary.
- `units._UNITS` is the single table of public data units (SI unit, scale, offset). A declared
  difference quantity converts by scale only, so `"5 degC"` as a temperature difference is 5 K.
- Do not perform database I/O, logging or mutate global state during calculations.
- `Fluid` definitions in `core.types.fluid` own immutable overrides and cache their
  `FluidProperties` snapshot; physics must not import types at runtime (`hydraulics` imports
  `Stream` and `Fluid` for type checking only).
- Do not hide undefined diagnostics as valid numbers. The receiving aquifer's unconfigured
  drainage radius leaves radial estimates unavailable while its pressure-flow model works.
- Inputs outside a correlation's domain raise `gm.errors.PhysicsRangeError` instead of dividing
  by zero or returning NaN: zero flow or CO2 pressure where a correlation divides by them or
  takes their logarithm, a negative flow that gives a complex corrosion or erosion rate, NORSOK
  underflow near 360 °C, and a zero liquid superficial velocity in Beggs–Brill. Unsupported
  model names raise `UnknownCorrelationError` and missing chemistry raises
  `MissingChemistryError`.
- The Beggs–Brill flow-regime map follows Beggs and Brill as revised by Brill and Beggs, with
  boundaries at no-slip holdup λ = 0.01 and λ = 0.4. A no-slip holdup of exactly 0.4 takes the
  upper range (intermittent for L3 < Fr <= L4, distributed for Fr > L4); it formerly matched no
  regime and divided by zero. Two-phase reverse flow uses the mirrored friction of forward flow.
- Preserve original numerical cases in `tests/fixtures/golden_values.json`, checked by
  `tests/unit/test_golden.py` and the physics unit tests. Intentional changes require a
  `NOTE(refactor):` sentence in the docstring and measured or physical evidence; see
  [refactor-notes.md](refactor-notes.md).
