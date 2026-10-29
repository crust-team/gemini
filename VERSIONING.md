# Versioning and Release Notes Policy

This repository uses **Semantic Versioning (SemVer)** and **Keep a Changelog**.

## Versioning scheme

Version format: `MAJOR.MINOR.PATCH`

- **MAJOR**: incompatible API or behavior changes.
- **MINOR**: backward-compatible feature additions.
- **PATCH**: backward-compatible bug fixes and small improvements.

The current version is defined twice and the two must agree: `version` in the `[project]` section
of `pyproject.toml` and `__version__` in `gemini/__init__.py`;
`tests/unit/test_public_api.py` checks that they are equal.

## Release notes source of truth

- Release notes are maintained in [`CHANGELOG.md`](./CHANGELOG.md).
- New work is recorded under `## [Unreleased]`.
- At release time, move relevant items from `Unreleased` to a new version section.

## Recommended release process

1. Ensure `CHANGELOG.md` (`Unreleased`) is up to date.
2. Choose next SemVer number (`MAJOR.MINOR.PATCH`).
3. Update the version in `pyproject.toml` and `__version__` in `gemini/__init__.py`.
4. Create a new section in `CHANGELOG.md`:
   - `## [X.Y.Z] - YYYY-MM-DD`
5. Commit the version/changelog changes.
6. Tag the release commit:
   - `git tag vX.Y.Z`
   - `git push origin vX.Y.Z`
7. Publish a GitHub Release using the matching changelog entries.

## Changelog categories

Use these headings when relevant:

- `Added`
- `Changed`
- `Deprecated`
- `Removed`
- `Fixed`
- `Security`

