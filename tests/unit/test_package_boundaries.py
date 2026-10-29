"""``gemini.utils`` and ``gemini.errors`` are leaf packages that import nothing else from GEMINI."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


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


@pytest.mark.parametrize("package", ["utils", "errors"])
def test_leaf_package_imports_only_itself(package):
    """Every import is the standard library, a dependency, or the package itself."""
    offending = {}
    for path in sorted((ROOT / "gemini" / package).rglob("*.py")):
        names = imported_modules(path)
        bad = {
            name
            for name in names
            if name.startswith(".")
            or (name.split(".")[0] == "gemini")
            and not name.startswith(f"gemini.{package}")
        }
        if bad:
            offending[path.name] = sorted(bad)
    assert offending == {}
