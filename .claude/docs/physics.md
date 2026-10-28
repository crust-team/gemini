# Core Physics Rules

`gemini/core/physics` holds physics that more than one component can use.

- One module per topic: `units`, `constants`, `fluid`, `geometry`, `hydraulics`,
  `heat_transfer`, `chemistry`, `corrosion`, `erosion` (add `thermodynamics` when needed).
- Plain typed functions, SI in and out. Use small Pydantic models or frozen dataclasses only for
  structured results (`PathResult`, `FluidProperties`, `PipeSection`).
- Every function docstring lists parameters and returns with units and gives the reference
  (author, year, title or standard, page/equation).
- Correlations that need non-SI units internally (Beggs–Brill, ESP curves, erosion) convert at the
  function boundary with `units`.
- Selecting between correlations uses a `Literal[...]` argument and raises `ValueError` on an
  unknown name.
- No state, no I/O, no logging inside physics functions.
- Do not add standalone `utils.py` or `helpers.py`; a function belongs to a topic module.
