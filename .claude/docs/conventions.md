# Implementation Conventions

## General rules

- Solve the requested task with the smallest clear implementation.
- Do not add abstractions, base classes, factories, configuration, or layers for hypothetical
  future needs. The only shared base classes are the ones in `gemini/core/base`.
- Prefer direct, readable code over clever or generic code.
- Keep functions focused, but do not split a short calculation into unnecessary wrappers.
- Reuse an existing pattern before introducing a new one. A new component looks like the
  existing ones.
- Add comments only when they explain a decision, an assumption, or a reference that the code
  cannot express. Physics formulas get the reference (paper, standard, page) in the docstring.
- Keep code compatible with black, isort (profile black) and flake8 with docstrings, line length
  100, as configured in `pyproject.toml`.
- Never change numerical behaviour silently. If you change a result, say why in the commit and
  update the affected test values on purpose.

## Package layout

- `gemini/core` holds what every part uses: `base` (Component, Stream, Unit, UnitModule),
  `physics` (generic physics and units), `plant`, `data`, `engine`, `modes`.
- `gemini/components/<category>/<name>.py` holds exactly one component per file. No
  per-component folders, no helper files next to components.
- `gemini/design`, `gemini/optim`, `gemini/agentic` build on `core` and `components`.
- Dependencies flow one way: `core` ← `components` ← `design` / `optim` ← `agentic`.
  `core` never imports `components` except through the registry's discovery;
  a component never imports another component.

## Imports

- Order imports as standard library, third-party packages, then local modules.
- Import physics modules and qualify their members: `hydraulics.darcy_weisbach_dp(...)`,
  `units.bar_to_pa(...)`, instead of importing many names.
- Direct symbol imports are fine for small, stable names: `Component`, `Stream`, `Health`,
  Pydantic's `BaseModel` and `Field`.
- Do not create re-export modules only to shorten imports. Category `__init__.py` files only
  re-export the component classes of that category.

Example:

```python
from pydantic import BaseModel, Field

from gemini.core.base.component import Component
from gemini.core.base.stream import Stream
from gemini.core.physics import hydraulics, units
```

## Units

- Everything inside the package is SI: K, Pa, kg/s, m³/s, m, W, J, s.
- Convert only at the edges (reading `.param` files or CSV data, examples, plots), always with
  `gemini.core.physics.units`. No inline magic numbers such as `* 1e5`, `+ 273.15`, `/ 3600`.
- Every Pydantic field states its unit in `description`, e.g. `"Wellhead pressure [Pa]"`; use
  `[-]` for dimensionless values.

## Errors

- Validate inputs with Pydantic models; do not write manual `if key not in dict` checks.
- Raise `ValueError` for invalid physical states (negative flow where not allowed, unknown
  correlation name) with a message naming the component and the value.
- Raise `NotImplementedError` only for declared placeholder components.
- Never `print` errors and continue; never swallow exceptions in physics code.

## Data and configuration

- Sensor tag names and plant-specific settings live in plant configuration (`.param`,
  `plant.conf`), never in component code.
- Conversion from GEMINI `.param` keys to component parameters lives only in
  `gemini/core/plant/param_mapping.py`.

## Validation

Run after every change:

```bash
poetry run black --check gemini tests
poetry run isort --check-only gemini tests
poetry run flake8 gemini tests
poetry run pytest tests
```
