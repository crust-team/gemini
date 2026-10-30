# Versioning and Release Notes Policy

This repository uses **Semantic Versioning (SemVer)** and **Keep a Changelog**.

## Versioning scheme

Version format: `MAJOR.MINOR.PATCH`

- **MAJOR**: incompatible API or behavior changes.
- **MINOR**: backward-compatible feature additions.
- **PATCH**: backward-compatible bug fixes and small improvements.

While the version is below 1.0, a breaking change to a public name or return field raises MINOR
(`0.2.0`) and an addition or a fix raises PATCH (`0.1.1`).

The version has one source: `version` in the `[project]` section of `pyproject.toml`.
`gm.__version__` reads it, and the public-API snapshot, checkpoints and saved results record it.

## Release notes source of truth

- Release notes are maintained in [`CHANGELOG.md`](./CHANGELOG.md).
- New work is recorded under `## [Unreleased]`.
- At release time, move relevant items from `Unreleased` to a new version section.

## Recommended release process

1. Ensure `CHANGELOG.md` (`Unreleased`) is up to date.
2. Choose next SemVer number (`MAJOR.MINOR.PATCH`).
3. Update the version in `pyproject.toml`.
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

