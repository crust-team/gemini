# Implementation conventions

Write for Python 3.11, the oldest supported version (3.11 to 3.14), and use Black, isort,
100-character lines and Flake8 with docstrings. Preserve captured numbers. Use SI internally: K, Pa,
kg/s, m, W, J and s. Record an intentional physical or numerical decision as a `NOTE(refactor):`
sentence in the docstring of the function, class or test that makes it, with its explanation and
regression evidence, and list lasting decisions in [refactor-notes.md](refactor-notes.md).

## Dependencies

A package may import only the packages to its left:

`gemini.utils`, `gemini.errors` ← `gemini.backends` ← `gemini.ops` ← `gemini.physics`
← `gemini.types` ← `gemini.backends.runtime` ← `gemini.modules` ← `gemini.graph`
← `gemini.utils.data` ← `gemini.engine` ← `gemini.utils.legacy` ← `optim`, `analysis`,
`economics`, `checks`, `testing`, `profiles` ← `gemini/__init__`.

Three files and folders live in a package lower in the order than their own place in it:
`gemini/backends/runtime.py`, `gemini/utils/data/` and `gemini/utils/legacy/`. They stay safe
because neither `gemini/backends/__init__.py` nor `gemini/utils/__init__.py` imports them, so
importing the lower package never loads them.

`gemini.backends` and `gemini.ops` sit below the physics because physics is written with the
ops; `gemini.graph` sits above `gemini.modules` because its tracer runs module calls (see
[native-engine.md](native-engine.md)).

`gemini.utils` (its topic files, not `data/` and `legacy/`) and `gemini.errors` are leaf packages:
they import only the standard library, installed dependencies and themselves, never another part
of `gemini` (`tests/unit/test_package_boundaries.py` enforces this). There are two documented exceptions to
the order. `gemini.physics.hydraulics` imports `Stream` and `Fluid` for type checking only, and
`Stream.__init__` in `gemini.types.flows` imports `gemini.backends.runtime` inside the function to read the
default fluid, because a module-level import would form a cycle through `gemini.types.fluid`.
`gm.plants.convert_legacy` imports `gemini.utils.legacy` inside the function, because the legacy
bridge sits above `gemini.modules`.
`gemini.utils.data` imports no module or engine code and `gemini.utils.legacy` imports no engine
code (the same test file enforces both).

Packages outside `gemini.utils.legacy` never interpret old project names, tags, tables or node
mappings. Old-format knowledge stays in `gemini.utils.legacy`, which is internal; its one public entry is
`gm.plants.convert_legacy(folder)`.
Equipment performs no file or database access. Calibration predicts only through public replay.
A plant is data: a `Plant` (`gm.Plant`) is built from `add` and `connect` or read from a format 2
spec (`gm.plants.from_spec`), and the spec file is the stored plant file. Only leaf modules and the
documented special cases (`HeatingSubstation`, `CoolingSubstation`, `ATESPlant`) are handwritten
`Module` subclasses; a handwritten root is written to the same format with its class as `type`.

## Public API freeze

The public API is frozen: [api.md](api.md) lists it. `gm.__version__` is the one version, read from
`version` in `pyproject.toml`. Below 1.0 a breaking change to a public name or a return field raises
the minor number (`0.2.0`) and an addition or a fix raises the patch number (`0.1.1`), in the same
commit, with a line in the change log of [api.md](api.md). `tests/unit/test_public_api.py` compares
against the stored snapshot `tests/fixtures/public_api.json`, which records the version and may only
change together with it: regenerate it with `tests/fixtures/capture_public_api.py` and add its hash
to `SNAPSHOTS` for the new version; never edit the hash of a released version.

## Module rules

**Physics lives in `gemini/physics/` or a `_physics.py`.** Modules declare and wire; they never
define physics. `gemini/physics/` keeps the textbook formulas and anything more than one category,
or `analysis`, `optim`, `economics` or `checks`, reads. Physics of one category lives in
`gemini/modules/<category>/_physics.py`, which imports only `gemini.physics`, `gemini.ops`,
`gemini.types` and `gemini.errors`, never another category's `_physics.py`; when a second category
needs a function it moves up into `gemini/physics/`. Its functions keep `@ops.physics` and stay
traceable on every backend. Reuse existing physics functions wherever possible and combine them; add
a new physics function only when nothing existing can do the job, and generalise an existing one
rather than writing a second copy. Never write a formula inside a module, and never write the same
formula twice.

**Helpers live in `gemini/modules/_utils/`.** A file under `gemini/modules/` that is neither a module
nor a category (`balance`, `burner`, `container`, `description`, `design`, `parameter`, `registry`,
`serialization`, `sorption`, `wiring`) goes there; `module.py` and the category folders stay. A class
in `_utils` belongs to no category, and the public names stay in `gm.modules`.
Fitting and calibration belong in `gm.analysis` or `gm.optim`, not in modules.

1. Assign declarations and children only in `__init__`, after `super().__init__()`.
2. Constructor sections are `# Modules`, `# Parameters`, `# Inlets`, `# Controls`,
   `# Boundaries`, `# States`, `# Outputs`, `# Outlets`, in that order, with empty sections
   omitted. Stateful equipment declares `State(kind, default=...)` values and implements
   `_advance_states(self, inlets, outlets, dt)`; see [modules.md](modules.md#state-and-health).
3. Controls are settable commands; boundaries are uncontrollable external conditions.
4. `forward` is exactly `forward(self, inlets)` and reads declared streams through the immutable
   `Ports` mapping, such as `inlets.fluid_in`. Controls and boundaries are applied before the call
   and read as plain attributes such as `self.frequency`.
5. `forward` sections are `# Modules` and `# Outlets`, in that order with empty sections omitted.
   Only composites use `# Modules`; `forward` never assigns an attribute on `self`.
6. Leaves assign every plain output in `_compute_outputs(self, inlets, outlets)`. Composites use
   `Output.of` and `Output.ratio` declarations with direct references and additive outputs
   without a formula, which sum their descendant leaves; they override `_compute_outputs` only
   to record their own value for such an additive output.
7. End every `forward` with `outlets = dict(...)`, the outlets in declaration order and then the
   drawn inlets, then `return outlets`.
   Zero- and one-outlet modules use the same dictionary shape.
8. Do not construct `ModuleResult` in module code; `Module.__call__` creates it.
9. Keep value arguments out of `__init__`; structural tree-shape arguments are the exception.
   Build a configured module with `ESP().update_params(...)`.
10. Never declare metadata or lists that `Module` derives.
11. Inlets and outlets carry a `Stream` or a `Power`: see [ports](modules.md#ports). A single
    `Power` inlet is drawn: the module computes it in `forward` and returns it under the port's
    name.
12. Pre-hooks are exactly `(module, inlets)` and forward hooks are exactly
    `(module, inlets, outlets)`.

Use dotted module paths consistently. Binding groups are `controls`, `boundaries`, `inlets`,
`measured` and `state`. Reject unknown ports and parameters. In replay a missing observation
skips only its measured twin; in simulation it skips the step. Never disguise a thermal-only
audit as full first-law closure or tune against a holdout merely to meet a threshold.

Examples live under `examples/<area>/<category>/NN_<name>.py`; the legacy bridge example
`examples/legacy/00_gemini_project_bridge.py` is the one example without a category folder.
Shared artifacts live in `examples/shared/`, and generated output goes under ignored `runs/`.

## Naming

Every port name is `<role>_in` or `<role>_out`. A module with one circuit uses `fluid_in` and
`fluid_out`. Splitter and mixer branches are `branch1_out`, `branch2_out` and `branch1_in`,
`branch2_in`, with `fluid_in` or `fluid_out` for the common side. The roles are:

| Group | Roles |
| --- | --- |
| Two sides of an exchanger or a machine | `hot`, `cold`, `source`, `sink`, `generator`, `chilled`, `cooling` |
| Storage and circuits | `charge`, `discharge`, `supply`, `return`, `production`, `injection` |
| Carriers | `gas`, `liquid`, `fuel`, `grid`, `excess`, `flue`, `power`, `heat`, `loss`, `air`, `wet_air`, `waste`, `chemical` |
| Wells and rock | `wellhead`, `bottom`, `sandface` |
| One circuit and branches | `fluid`, `branch<N>` |

Add a role only when no existing one fits, here and in [glossary.md](glossary.md).
`test_every_port_follows_the_naming_rule` in `tests/unit/test_code_quality.py` checks every port of
every registered module against the rule and this list. A port's label says what may be connected:
`Inlet(Stream, kind="hot_water")`, one of `gm.streams.names()`; `kind` means only this label, and the
first argument of every declaration is its `type`.

Outputs derived from a port field are named `<port>_<field>`, for example `hot_out_T`. Controls
and boundaries name the commanded quantity in full words (`frequency`, `production_rate`);
setpoints are `<quantity>_setpoint` (`pressure_setpoint`, `temperature_setpoint`). The `Stream`
field symbols `m_dot`, `T` and `p` are reserved for `Stream` fields and binding field keys.

[glossary.md](glossary.md) holds the one name of each concept. Elsewhere use full words, not
abbreviations. Booleans read as questions (`is_leaf`,
`is_initialized`, `has_input_value`). Add an SI unit suffix only where the type does not carry the
unit, for example the summary column `energy_J` or the constant `TEST_BUDGET_S`; declared
quantities carry their unit and never repeat it in the name.

Never name the framework the module design resembles, in code, docstrings, examples or
documents; describe the concept itself. `test_no_framework_names_in_tracked_text_files` in
`tests/unit/test_code_quality.py` fails on any occurrence in a tracked file.

## Comments

The only comments allowed in code are:

- the fixed section headers: in `__init__` `# Modules`, `# Parameters`, `# Inlets`,
  `# Controls`, `# Boundaries`, `# States`, `# Outputs`, `# Outlets`; in `forward` `# Modules` and
  `# Outlets`;
- tool directives with a specific code: `# noqa: <code>`, `# type: ignore[<code>]` and
  `# pragma: no cover`.

Everything worth explaining (why, units, sources, non-obvious physics or numerics) goes into
docstrings. Intentional physical or numerical decisions are a `NOTE(refactor):` sentence in the
docstring, never a comment. `test_only_section_headers_and_tool_directives_are_comments` in
`tests/unit/test_code_quality.py` checks every Python file in `gemini/`, `examples/`, `tests/` and
`scripts/`.

## Code quality

- Flat code: nest at most three blocks deep (an `elif` chain counts once), prefer guard clauses
  and write no `else` after `return` or `raise`.
- Small functions: about 40 lines of body and one job each. The documented exceptions, each with
  its reason, are listed in `LONG_FUNCTIONS` in `tests/unit/test_code_quality.py`.
- McCabe complexity at most 10 (`max-complexity = 10` in the `[tool.flake8]` section of
  `pyproject.toml`).
- Just enough code: no dead code, unused options or parameters, speculative generality or golfed
  one-liners.
- Clear names, as in [Naming](#naming).
- Explicit errors: raise a `gm.errors` class (see [errors.md](errors.md)), never a bare
  `except`, and no silent fallback that hides a failure.
- A bug gets a failing test first; the fix makes it pass.

A module holds no `*`, `/`, `**`, numeric literal other than 0 and 1, `math.*`, NumPy maths or
`ops.exp`-style call: `test_modules_hold_no_formulas` scans `gemini/modules/` except `plants/`, with
the exceptions and their reasons in `FORMULA_EXCEPTIONS`. Bookkeeping of like quantities (`inlet.p -
drop`, `m_1 + m_2`) stays in a module; a default value is a named physics constant.
`test_no_two_physics_functions_share_a_body` compares the normalised bodies of the physics functions,
so a copy with renamed arguments fails; a body of one operator on two names is a definition and is
not compared, and different relations of one form are listed in `SAME_FORM`.
`tests/unit/modules/test_glossary.py` checks every name against [glossary.md](glossary.md).

Enforcement: `tests/unit/test_code_quality.py` checks nesting
(`test_functions_nest_at_most_three_blocks`), function length
(`test_functions_are_short_or_documented_exceptions`), `else` after an early exit
(`test_no_else_after_an_early_exit`), builtin raises (`test_package_code_raises_gemini_errors`),
comments and framework names. Flake8
(`make lint` and the Lint workflow) checks complexity (C901), bare `except` (E722), unused imports
and variables (F401, F841) and docstrings. The remaining points (just enough code, names and
test-first bug fixes) are checked in review.

## One implementation per concept

- No concept has two implementations; the only thing that differs is the backend. A rule, a
  formula, a check, a message or a result structure is written once, with `gemini.ops`, and every
  caller runs that source.
- Behaviour is identical on every backend: values, error class and message, skips, `Results`
  structure with children, output types, callbacks and health, bit-identical on the Python path and
  within `1e-12` on NumPy.
- A direct call (`esp(fluid_in=...)`, `pumps.head(...)`) is **eager**: the same `forward`, the same
  ops, no graph, on the Python backend. It is not a second implementation. The eager scope below
  makes plain operators safe in it; a function never has a "checked" and an "unchecked" version.
- Physics code uses plain operators (`/`, `**`, `-`) where the Python and NumPy results agree. A
  public function of `physics` carries `@ops.physics`; a module method that a user can call
  directly with raw operators carries it too. Do not add `Failed` handling anywhere in physics or
  modules.

## Implicit mechanisms

The package avoids hidden behaviour. These are the only implicit mechanisms left, each with the
reason it is needed:

- `Module.__setattr__` registers what `__init__` assigns: a `Parameter`, `Inlet`, `Control`,
  `Boundary`, `State`, `Output` or `Outlet` goes to its ordered registry and a `Module` becomes a
  child with a dotted path. Assigning to a declared name sets the parameter, persists the control or
  boundary (inside a running call, it changes that call only) or records the output of the running
  call. Constructors therefore read as plain assignments in section order, and `esp.frequency = 50`
  persists a command.
- `Module.__getattr__` resolves names that are not ordinary attributes: parameter values, the
  current control and boundary values (running call, then persisted value, then default),
  outputs recorded in the running call, state values at the start of the running step (the
  initial states outside a step), and otherwise the port and output declarations. This lets
  `forward` and `_compute_outputs` read `self.thermal_conductance` or `self.frequency` as plain values.
- The values of one call live in one `_Call` record held in the `_current_call` context variable
  of `gemini/modules/module.py`. Modules keep no per-call state on `self`, so nested,
  re-entrant and concurrent calls stay separate and composite formulas can read the results of
  their children's calls. During `Module.step` each call record also points to the one `_Step`
  record (time step and state trees), so a composite steps its stateful descendants through its
  ordinary `forward` instead of a second, hand-written step method.
- `gm.no_outputs()` and `gm.runtime.settings()` are context settings built on
  `gemini.utils.context.ContextSetting`: a context variable change usable as a `with` block and
  as a decorator, restored on exit.
- `describe`, `parameter_schema` and `validate_params` work on a class and on an instance through
  `_ClassOrInstance` in `gemini/modules/module.py`: on a class they run on a new instance,
  because a module's declarations exist only once `__init__` has run.
- `Module.category` is `_FolderCategory` in `gemini/modules/module.py`, a descriptor that reads
  the folder from the import path of the class, so the folder is the one source of a module's
  category. A class from outside assigns `category` itself, which replaces the descriptor.
- `class_path`/`import_class` in `gemini/modules/module.py` are the only import-by-string.
  Only checkpoints use them: a checkpoint names the plant class (`Plant`, or a handwritten root)
  whose `from_dict` rebuilds the tree from the spec it stores. A plant file names registry types.
- A plant child that sits in a cycle of composites but not of leaves is *opened*: the parent's
  `forward` calls its children directly, in the order the connections give (see
  [native-engine.md](native-engine.md), section 14). The call order is never configured by hand.
- Attribute access on mappings: `Ports` and `Values` derive from
  `gemini.utils.mappings.AttributeMapping`, so `result.outlets.fluid_out` equals
  `result.outlets["fluid_out"]`, and `Results[path].field` returns a pandas Series through
  `ModuleSeries.__getattr__`.
- `Plant.forward` runs a module with an `offered` outlet twice in one step: `Module.offer` first,
  which no call records, then its call. A drawn inlet takes its value from what `forward` returns,
  so `ModuleResult.inlets` shows what was drawn. Both are needed because the value on a connection
  can travel against the energy ([ports](modules.md#ports)).
- Two optional method protocols: a module that defines `capex(assumptions)` returning a `Cost`
  declares its own cost for `gemini.types.cost.total_cost(plant, assumptions)`, which looks the method up by name; a
  module that overrides `health(result, measured)` gets a diagnostic, which the engine calls
  after each replayed twin (the base method returns `None`, meaning not assessed).

- Operator overloading on `gemini.ops.Operators`: a `Constant` (`physics/constants.py`)
  and a traced `gemini.graph.Proxy` route `+`, `*`, `<`, ... through `gemini.ops.dispatch`, so
  one physics source runs on floats, arrays and traced values. A constant acts as its float on
  concrete values and becomes a named graph input in a trace. The math functions (`ops.log`,
  `ops.sqrt`, `ops.maximum`, ...) and `ops.truediv`/`ops.pow` never raise or warn on an operand
  that is invalid in the branch a `where` does not select: they return `inf` or `nan` as NumPy
  does. `where` branches are plain values, never callables; `None` is allowed as a branch.
  For speed the op functions evaluate plain scalars (`float`, `int`, `bool`, `None`, NumPy
  `float64`/`bool_`) directly on the Python backend and a `Constant` computes its operators on its
  value without `dispatch`; arrays, other NumPy scalars, traced values and an active
  `backends.settings(backend=...)` take the full `dispatch` path. A `Constant` is not a `float`.
- The eager scope (`gemini/ops/scope.py`, `gemini/ops/failed.py`), entered by `@ops.physics` and
  by `Module._run`, is what makes a direct call behave like the graph. The outermost entry enters
  `np.errstate(all="ignore")` and gives plain Python numbers to the function as NumPy scalars (an exact
  `float` as `np.float64`, an exact `int` as `np.int64`; a module call wraps its parameters, on
  first read, its controls, states and inlet fields), so `/` by zero, an invalid `**` and an overflow give `inf` or `nan` silently, as
  on arrays. Leaving the outermost scope converts scalars back to `float` and `int`, `np.bool_` to `bool`,
  recursively, so results, outputs and outlet streams never hold NumPy scalars. Recorded outputs
  read back inside a call are wrapped too; results of child calls stay plain floats, so a
  composite that divides child values uses `ops.truediv`. Arrays or traced values among the
  arguments leave the scope unwrapped. `Module._scalar_mode()` (`WRAP` by default) lets a module
  ask for `PLAIN`: the ESP does under `precision="float32"`, the one module that honours it,
  because an `np.float64` scalar would promote the float32 coefficients; its
  `pumps.esp_efficiency` keeps `ops.truediv` for that reason. A nested scope costs a
  context-variable read.
  A failing `ops.check` on concrete scalars raises the real error marked as coming from a check;
  `@ops.physics` returns it as a `Failed` value at the function boundary, so
  `where(stopped, 0.0, checked_function(x))` drops the error of the unselected branch and keeps the
  selected one, like the graph's error codes. A `Failed` carries through every op, raises when used
  as a number (`bool`, `float`, `int`, `format`, a `Stream`, a `Declaration`) and raises its error
  when it leaves the outermost scope. A failing `check` on an eager array raises at once, for the
  first failing row; tests compare arrays through `gemini.graph.run_function`. In a trace the graph
  does the same: a check recorded in a physics function guards that function's traced results (all
  of them, through an `identity` node for a passed-through argument) and reaches an outer function
  through data, and a check outside any physics function (inline in `forward`) guards every graph
  output, as it raises at once when eager. Never put the `repr`
  of a physical value in a message (it reads `np.float64(1.0)`) and use `ops.round`, not `round`.
- A module holds its `GraphCache` in `_graph_cache` (`None` until `gemini.graph.graph_cache` first
  asks for it), so traced graphs outlive an engine and a run function does not trace the plant
  again. It sits on the module because a graph refers to its module, so a cache outside would keep
  the module alive; a copied or pickled module starts with an empty cache
  (`GraphCache.__reduce__`).
- During a trace the `_Call` record carries the traced parameter values, which
  `Module.__getattr__` returns instead of the stored values, and records outputs without
  validating them (`gemini/graph/tracer.py`).

Adding another implicit mechanism needs a reason of the same weight and an entry here.
