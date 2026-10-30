# Errors

`gemini/errors/` defines GEMINI's exception and warning classes. Users reach them as
`gm.errors.<Name>`. It is a leaf package that imports nothing else from `gemini`
(`tests/unit/test_package_boundaries.py`).

Every class derives from `GeminiError` (or `GeminiWarning`) and from the matching built-in
exception, so `except ValueError` keeps catching `gm.errors.UnitError`. Catch `GeminiError` to
handle every GEMINI error. New code raises one of these classes for every deliberate error; the
exceptions are the topic files of `gemini.utils`, which cannot import them, pydantic validators, which must raise
`ValueError` (pydantic reports it as a `ValidationError`), and the Python protocol errors
(`NotImplementedError`, and `AttributeError` from the `__getattr__` of non-module classes).
`test_package_code_raises_gemini_errors` in `tests/unit/test_code_quality.py` enforces this.

## Hierarchy and use

`base.py`:

- `GeminiError(Exception)`: root of every class below. It takes `path=`, `code=` and
  `suggestions=` as keywords and `to_dict()` returns `{class, message, path, code, suggestions}`
  as plain JSON, the shape of `422` details and tool results. `code` defaults to the class
  attribute and must be one of `CODES`.
- `ValidationError(ValueError)`: a value, a spec or a run input breaks a documented rule.
  `DeclarationError` and `BindingError` derive from it.
- `Cancelled`: a callback stopped a run; the ticks already committed stay readable.
- `NotImplementedYet(NotImplementedError)`: the name is final, its work lands in a later step.
- `GeminiWarning(UserWarning)`: root of warnings; `legacy.to_plant` lists the old fields it cannot
  map in one `GeminiWarning`.

`module.py`, defining, configuring and calling modules:

- `DeclarationError(TypeError, ValueError)`: a class or tree defined wrongly: declarations before
  `super().__init__()`, replaced declarations, invalid child names, cycles, invalid declaration
  values, hook signatures (`module.py`, `declarations.py`). A traced call raises it from the
  graph checks of the declared bounds (`gemini/graph/limits.py`) with the class
  `Declaration.validate` raises on a plain call.
- `UnknownNameError(ValueError)`: unknown module path, parameter, control, boundary or runtime
  setting (`module.py`, `runtime.py`).
- `UnknownPortError(KeyError, AttributeError)`: unknown name in a `Ports` or `Values` mapping.
- `UnknownMemberError(AttributeError)`: a module has no child, declaration or port with the
  requested attribute name (`Module.__getattr__`). It is an `AttributeError` for `hasattr`,
  `getattr` with a default, `copy` and `pickle`. The close-match suggestion is built only when
  the message is read, from the module the error holds; copying or pickling stores the finished
  message.
- `CallError(TypeError)`: wrong, missing, duplicate or invalid call arguments and inlet streams.
- `OutletError(TypeError, ValueError)`: `forward` returned something other than the declared
  outlet dictionary.
- `MissingValueError(RuntimeError, TypeError)`: a parameter, control or boundary has no value.
- `OutputError(RuntimeError)`: an output assigned outside output computation or left unassigned,
  or an `Output.of` descendant not called exactly once.
- `FormulaError(TypeError, ValueError)`: an `Output.of`, `Output.ratio` or automatic-sum formula
  cannot be resolved.
- `TraceError(TypeError)`: a module cannot be traced into a computation graph: Python control
  flow or a conversion on a traced value (`if`, `and`, `float()`, formatting), a stateful root,
  float32 precision, a pre-hook on the root, a forward hook that only reads, or a composite child that
  cannot be recorded. The graph runner catches it and runs that module as a plain call (a graph break,
  `gemini/graph/runner.py`); a leaf child of a composite that raises it becomes a break node
  instead. Break nodes also use it for a probe or row that fails to build the traced fluids, and
  `Engine` keeps the reason of a twin it could not trace in `engine.graph_breaks`.
- `ConfigurationError(ValueError)`: equipment design data missing or inconsistent at call time,
  including calibration requests that do not fit the plant (`module.py`, equipment,
  `optim/calibrate.py`).

`engine.py`, data, runs and files:

- `DatasetError(TypeError, ValueError)`: a dataset or profile cannot be built or read.
- `ClockError(KeyError, ValueError)`: an invalid clock, or a timestamp that is not a tick.
- `BindingError(ValidationError)`: bindings that do not match the plant or the dataset, checked
  when the run is planned (`step.py`, `optim/calibrate.py`). Bound columns that the run input lacks
  are listed together with the code `missing_column` and a close-match suggestion.
- `MissingMeasurementError(ValueError)`: a bound observation is missing at one tick; the engine
  catches it and counts the skip, and `str(error)` is the reason in `Results.skip_counts` and the message of its `missing_value` row
  in `Results.errors()`.
- `StepError(ValueError)`: a replayed twin failed under `on_error="raise"`; the cause is chained.
- `CheckpointError(RuntimeError, ValueError)`: a checkpoint cannot be saved, loaded or resumed
  (`checkpoint.py`, `engine.py`, `run.py`, `clock.py`).
- `PlantFormatError(TypeError, ValueError)`: a plant file or state with another version, plant
  type or module tree.
- `UnknownResultError(KeyError, AttributeError)`: an unknown results module path or field.

`physics.py`, units and correlations:

- `UnitError(ValueError)`: an unknown unit, or one that cannot convert to the requested unit
  (`units.py`, `flows.py`, `results.py`, `profile.py`).
- `PhysicsRangeError(ValueError)`: an input outside a correlation's domain, such as zero or NaN
  flow where a correlation divides by it (physics and equipment).
- `SolverError(PhysicsRangeError)`: an iterative solve did not converge (`loops.close_loop`).
- `UnknownCorrelationError(ValueError)`: an unsupported correlation, model or material name.
- `MissingChemistryError(ValueError)`: a correlation needs fluid chemistry that was not given.
- `InsufficientDataError(ValueError)`: a fit or estimate with too few valid observations.

`legacy.py`:

- `LegacyFormatError(ValueError)`: an old project file that is missing, malformed or describes a
  plant the bridge cannot convert.

## Codes

`gm.errors.CODES` is the fixed tuple of `code` values; the backend puts them into `422` details,
so a code is never renamed without raising `gm.API_VERSION`. `gm.errors.ROW_CODES` maps every row
code of `Results.errors()` to its meaning.

| Code | Meaning |
| --- | --- |
| `error` | A GEMINI error with no more specific code |
| `invalid_value` | A value has the wrong type or shape |
| `out_of_bounds` | A value is outside its declared bounds |
| `missing_value` | A required value is absent |
| `invalid_unit` | A unit is unknown or does not fit the quantity |
| `unknown_name` | A module type, path, parameter, category or field does not exist |
| `unknown_port` | A port does not exist on that module |
| `invalid_call` | A module was called with wrong arguments |
| `invalid_format` | A document has the wrong structure |
| `old_format` | A plant file is older than the current format; use `gm.plants.migrate` |
| `migration_failed` | An old plant file cannot be migrated |
| `invalid_connection` | A connection breaks a wiring rule |
| `stream_mismatch` | The two ends of a connection carry different stream types |
| `ambiguous_port` | Automatic port matching found no port or more than one |
| `port_in_use` | An inlet already has a source, or an outlet already has a target |
| `loop_without_state` | A cycle has no connection of kind `state` |
| `invalid_binding` | A binding does not fit the plant or the data |
| `missing_column` | A bound column is not in the run input |
| `invalid_data` | Run input or a dataset cannot be read |
| `physics_range` | An input is outside the domain of a correlation |
| `solver_failed` | An iterative solve did not converge |
| `cancelled` | A callback stopped the run |
| `not_implemented` | The name is final, its work lands later |

## Message style

Write `<module path>: <field> = <value> <unit>; expected <what>[; did you mean 'x'?]`, for example
`units.convert: unit = 'K'; expected a unit of 'Pa' to convert from 'bar'`. Use
`gemini.utils.strings.did_you_mean` for the suggestion and `join_names` for lists of valid names.

## Adding a class

Add a class only for a situation no existing class describes. Put it in the file of its topic,
derive it from `GeminiError` (or `GeminiWarning`) and from the matching built-in exception, give
it a one-line docstring saying when it is raised, export it in `gemini/errors/__init__.py` (import
and `__all__`), and test it in the mirrored file under `tests/unit/errors/`. Then update this
document.
