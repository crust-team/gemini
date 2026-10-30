"""The package version: ``version`` in ``pyproject.toml`` is the one source.

A source checkout reads the file; an installed package has no such file and reads the same text
from its metadata, which the build copied from it.
"""

import re
import tomllib
from importlib import metadata
from pathlib import Path

DISTRIBUTION = "gemini-geothermal-suite-open"
"""The name in ``pyproject.toml``, under which an installed package finds its metadata."""

OLDEST_READABLE = "0.1.0"
"""Checkpoints and results files written before this version do not load."""

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"
_SEMANTIC = re.compile(r"\d+\.\d+\.\d+")


def package_version():
    """Return the version of the package."""
    if PYPROJECT.exists():
        return tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    return metadata.version(DISTRIBUTION)


def _parts(version):
    return tuple(int(part) for part in version.split("."))


def is_older(version, oldest=OLDEST_READABLE):
    """Return whether ``version``, read from a file, is before ``oldest`` or is not a version."""
    if not (isinstance(version, str) and _SEMANTIC.fullmatch(version)):
        return True
    return _parts(version) < _parts(oldest)
