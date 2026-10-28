# GEMINI Geothermal Suite

An installable Python package for geothermal equipment physics and time-series monitoring,
developed by TNO and partners in the Nieuwe Warmte Nu programme. Python **3.11** and
**Pydantic v2** are used for the component API. Package inputs and outputs use SI units.

## Install and run

From this directory:

```bash
pip install poetry
poetry install
poetry run python examples/01_esp_operating_point.py
poetry run python examples/04_doublet_chain.py
poetry run python examples/05_list_components.py
```

For library use, `pip install .` installs the `gemini` import package. Examples and sample
plant files live in the source checkout under `examples/` and `datasets/geothermal_example/`.
No external services are needed for the components, examples or CSV engine integration test.

```python
from gemini.core.base.stream import Stream
from gemini.core.engine.registry import create

boiler = create("boiler", {"fuel": "electric", "capacity": 100000, "efficiency": 0.95})
result, streams = boiler.compute(
    {"setpoint_T": 350},
    {"inlet": Stream(m_dot=10, T=300, p=1000000)},
)
print(result.duty, streams["outlet"].T)
```

## Package structure

- `gemini/core/base`: validated streams, component contracts, health, runtime unit interfaces.
- `gemini/core/physics`: units, fluid properties, geometry, hydraulics, heat transfer,
  chemistry, corrosion and erosion.
- `gemini/core/plant`: configuration mappers, connected units and plant loading.
- `gemini/core/data`: CSV, InfluxDB and AVEVA drivers; an offline CSV reader with in-memory outputs.
- `gemini/core/engine`: time loops, registry and component-based monitoring modules.
- `gemini/components`: subsurface, pumps, treatment and heat equipment, one file per equipment type.
- `gemini/design`, `gemini/optim`, `gemini/agentic`, `gemini/core/modes`: reserved namespaces.

Implemented equipment includes ESPs, production/injection reservoirs and wells, boilers, and
counterflow/parallel heat exchangers. Injection/booster pumps, degassers, filters and blowdown
have explicit unmodelled compute methods. Filter clogging monitoring is available independently.

## Conventions and numerical compatibility

Read [AGENTS.md](AGENTS.md) and the linked [.claude/docs](.claude/docs/conventions.md) before
changing code. Component ports carry immutable `Stream` objects. Parameters, operating inputs,
returned output types and port names are validated on direct `compute()` calls.

GEMINI `.param` files retain their historical units and timestamped structure. Convert them
through `gemini.core.plant.param_mapping`. Corrosion and erosion rates retain the documented
`mm/year` output convention. ESP polynomial coefficients retain their historical US basis;
efficiency is now a fraction. The example pump has zero power coefficients.

`tests/golden/golden_values.json` contains the original physics baseline. Do not regenerate it
from the new API. `tests/golden/capture_golden.py` is a historical script intended to be run at
the phase-0 commit, where the original imports still exist. `runtime_values.json` additionally
records all eight legacy monitoring outputs from the first CSV interval, captured using the
phase-1 implementation (`193c9a8`) before rewriting the engine adapters.

Public components use physically consistent SI mappings. Compatibility adapters retain old
dashboard conventions, including the legacy IPR unit mismatch, ESP interval selection and
float32 polynomial evaluation. Search for `NOTE(refactor)` for their precise locations.
The injection example has an unconfigured zero drainage radius; radial diagnostics are `None`.

The doublet example registers a named constant brine model during configuration so reservoir,
well and pump streams use the same example density. The default `water`/`brine` properties remain
unchanged. It imposes flow and prints the injection pressure residual; no network solver is implied.

## Offline and service-backed monitoring

```python
from gemini.core.data.csv_memory import CSVMemoryReader
from gemini.core.engine.mainmodule import MainModule
from gemini.core.plant.loader import setup

reader = CSVMemoryReader(
    "datasets/geothermal_example/geothermal_example_dataset.csv",
    end_time="2024-06-07T00:15:00Z",
)
plant = setup("datasets", "geothermal_example", database=reader)
MainModule(plant).step()
print(reader.outputs)
```

Calling `setup` without a supplied reader uses the retained InfluxDB/AVEVA configuration path.
Supply the existing `INFLUXDB_URL`, `INFLUXDB_ORG`, `INFLUXDB_USERNAME`, `INFLUXDB_PASSWORD`, and
`INFLUXDB_BUCKET` environment variables when using that path. The runner does not load `.env`
files or start services at import time. External-service tests are skipped without credentials.

## Validation and API documentation

```bash
poetry run black --check gemini tests
poetry run isort --check-only gemini tests
poetry run flake8 gemini tests
poetry run pytest tests
poetry run sphinx-build -W -b html docs docs/_build/html
```

The workflows inline these commands. Documentation consists of the Python API reference;
GitHub Pages deployment runs only for `main`. See [CHANGELOG.md](CHANGELOG.md) and
[VERSIONING.md](VERSIONING.md) for release policy. This migration is unreleased.

## License and acknowledgments

[Apache 2.0](LICENSE). Supported by NWM innovatie: Datagedreven optimalisatie
aardwarmtesystemen, with TNO, Gaia Energy, HVC, Well Engineering Partners and Helin.
