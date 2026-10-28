# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Validated SI equipment components, streams, health hooks and automatic component discovery.
- Shared physics, parameter mappers, heat exchanger and boiler models, five runnable examples.
- Immutable physics golden values and offline CSV monitoring regression checks.
- Agent conventions in `AGENTS.md`, `CLAUDE.md` and `.claude/docs/`.

### Changed
- Consolidate the suite into the installable `gemini` Python package.
- Rewrite monitoring modules to use components while preserving the existing eight output tags.
- Move example plant data to `datasets/geothermal_example` and API documentation to `docs`.
- Return ESP efficiency as a fraction; report undefined radial diagnostics as unavailable.

### Removed
- Flask interface, application/UI workflows, container stack and platform launcher scripts.
- UI-only dependencies and obsolete model base classes; old import paths are not retained.

## [1.0.3] - 2026-10-13
## added
- parameters and tagnames of geothermal_example using csv data
### Fixed
- fix influxsb writing data float

## [1.0.2] - 2026-10-12
### Fixed
- fix grafana reverse-proxy authentication inside iframe

## [1.0.1] - 2026-08-20
### Fixed
- add python-dotenv package to pyproject.toml
### Changed
- more info for setting up environment variables in documentation
- change naming environment variables of OLLAMA and CHROMADB


## [1.0.0] - 2026-07-19

### Added
- Initial open-source release of the GEMINI Geothermal Suite.
- Initial release of the GEMINI Geothermal Model.
- Initial release of the GEMINI Geothermal Framework.
- Initial release of the GEMINI Geothermal Application.
  - Diagram Builder Application
  - ESP Monitoring Application
  - Productivity Application
  - Injectivity Application
  - Well Schematic Application
  - Well Integrity Monitoring Application
  - Time-series Visualization Application
  - Report Generation Application
  - Chatbot Application
- Initial release of the GEMINI Geothermal Interface.