# GEMINI Python package

GEMINI is TNO's geothermal digital-twin suite, organised as an installable Python package with equipment components, shared physics, plant configuration, data drivers, and a time-series monitoring engine. Component interfaces use Pydantic v2 and SI units. Preserve the captured numerical baseline when changing existing models.

## Layout

```text
.
├── gemini/
│   ├── __init__.py
│   ├── core/          # base, physics, plant, data, engine, modes
│   ├── components/    # subsurface, pumps, treatment, heat
│   ├── design/
│   ├── optim/
│   └── agentic/
├── tests/             # mirrors gemini; golden baseline
├── datasets/
│   └── geothermal_example/
├── examples/
├── docs/              # Sphinx API reference
├── pyproject.toml
├── README.md
├── CHANGELOG.md
└── LICENSE
```

## Read before coding

- [Conventions](.claude/docs/conventions.md)
- [Components](.claude/docs/components.md)
- [Physics](.claude/docs/physics.md)
- [Testing](.claude/docs/testing.md)
