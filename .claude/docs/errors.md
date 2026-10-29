# Errors

`gemini/errors/` defines every exception and warning GEMINI raises on purpose. Users reach them
as `gm.errors.<Name>`. It is a leaf package that imports nothing else from `gemini`.

Every class derives from `GeminiError` (or `GeminiWarning`) and from the matching built-in
exception, so `except ValueError` keeps catching `gm.errors.UnitError`. Catch `GeminiError` to
handle every deliberate GEMINI error.

| File | Classes |
| --- | --- |
| `base.py` | `GeminiError(Exception)`, `GeminiWarning(UserWarning)` |
| `module.py` | `DeclarationError`, `UnknownNameError`, `UnknownPortError`, `CallError`, `OutletError`, `MissingValueError`, `OutputError`, `FormulaError`, `ConfigurationError` |
| `engine.py` | `DatasetError`, `ClockError`, `BindingError`, `MissingMeasurementError`, `StepError`, `CheckpointError`, `PlantFormatError`, `UnknownResultError` |
| `physics.py` | `UnitError`, `PhysicsRangeError`, `UnknownCorrelationError`, `MissingChemistryError`, `InsufficientDataError` |
| `legacy.py` | `LegacyFormatError` |
