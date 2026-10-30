"""The one source of the package version."""

import tomllib

import pytest

from gemini.utils import version
from tests.fixtures import ROOT


def test_the_version_is_the_one_of_pyproject():
    """A source checkout reads ``pyproject.toml``."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert version.package_version() == project["project"]["version"]


def test_an_installed_package_reads_its_metadata(tmp_path, monkeypatch):
    """Without the file, the version comes from the package metadata."""
    monkeypatch.setattr(version, "PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(version.metadata, "version", lambda name: f"9.9.9 of {name}")
    assert version.package_version() == f"9.9.9 of {version.DISTRIBUTION}"


@pytest.mark.parametrize("stored", [1, None, "1", "0.0.9", "abc", "0.1", "0.1.0-dev"])
def test_what_is_not_a_version_since_the_oldest_is_older(stored):
    """Integers of the former layouts and malformed text count as older."""
    assert version.is_older(stored)


@pytest.mark.parametrize("stored", ["0.1.0", "0.1.7", "0.2.0", "1.0.0", "0.10.0"])
def test_the_oldest_version_and_later_ones_are_readable(stored):
    """Versions compare by number, not as text."""
    assert not version.is_older(stored)
