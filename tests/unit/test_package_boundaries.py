"""``gemini.utils`` and ``gemini.errors`` are leaf packages that import nothing else from GEMINI.

``gemini/utils/data`` and ``gemini/utils/legacy`` are the exception: they live in ``utils`` but sit
higher in the dependency order, so they have their own rule here.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
LAYERED = {"data": ("gemini.modules", "gemini.engine"), "legacy": ("gemini.engine",)}
"""Folders of ``gemini.utils`` above the leaf, with the packages each must never import."""


def imported_modules(path):
    """Return the absolute module names one file imports."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


def leaf_files(package):
    """Return the files of a leaf package, without the layered folders."""
    root = ROOT / "gemini" / package
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if path.relative_to(root).parts[0] not in LAYERED
    ]


def is_layered(name):
    """Whether an import names one of the layered folders."""
    return any(name.startswith(f"gemini.utils.{folder}") for folder in LAYERED)


@pytest.mark.parametrize("package", ["utils", "errors"])
def test_leaf_package_imports_only_itself(package):
    """Every import is the standard library, a dependency, or the package itself."""
    offending = {}
    for path in leaf_files(package):
        names = imported_modules(path)
        bad = {
            name
            for name in names
            if name.startswith(".")
            or (name.split(".")[0] == "gemini")
            and (not name.startswith(f"gemini.{package}") or is_layered(name))
        }
        if bad:
            offending[path.name] = sorted(bad)
    assert offending == {}


@pytest.mark.parametrize("folder", LAYERED)
def test_layered_folders_stay_below_what_they_must_not_know(folder):
    """The data package knows no modules or engine, the legacy bridge knows no engine."""
    offending = {}
    for path in sorted((ROOT / "gemini" / "utils" / folder).rglob("*.py")):
        bad = {name for name in imported_modules(path) if name.startswith(LAYERED[folder])}
        if bad:
            offending[path.name] = sorted(bad)
    assert offending == {}
