"""Enforce one mirrored unit-test module with real tests for every source file.

Every ``gemini/<path>/<name>.py`` except ``__init__.py`` (including ``gemini/utils/`` and
``gemini/errors/``) needs ``tests/unit/<path>/test_<name>.py`` defining at least one test
function. ``PLACEHOLDERS`` lists the mirror files that still hold only a docstring while their
owners write the tests; it is emptied once every file has a test and must never grow.
"""

import ast

from tests.fixtures import ROOT

SOURCE = ROOT / "gemini"
UNIT_TESTS = ROOT / "tests/unit"
PLACEHOLDERS = {
    "core/engine/test_callbacks.py",
    "core/engine/test_checkpoint.py",
    "core/engine/test_engine.py",
    "core/engine/test_step.py",
    "core/legacy/test__loader.py",
    "core/legacy/test_convert.py",
    "core/modules/plants/test_doublet.py",
    "core/modules/test_wiring.py",
    "core/physics/test_constants.py",
    "core/physics/test_erosion.py",
    "core/physics/test_geometry.py",
    "core/physics/test_heat_transfer.py",
    "core/physics/test_pumps.py",
    "core/types/test_flows.py",
    "core/types/test_results.py",
    "optim/test_calibrate.py",
}


def _mirror(source):
    """Return the unit-test path that mirrors one source file."""
    relative = source.relative_to(SOURCE)
    return UNIT_TESTS / relative.parent / f"test_{relative.name}"


def _defines_test(path):
    """Whether a test module defines a test function at module level or in a class."""
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")
        for node in ast.walk(ast.parse(path.read_text()))
    )


def _mirrors():
    """Yield every source file except package markers with its expected mirror path."""
    for source in sorted(SOURCE.rglob("*.py")):
        if source.name != "__init__.py":
            yield source, _mirror(source)


def test_source_files_have_mirrored_unit_tests():
    """Every source file has a mirrored unit-test module."""
    missing = [
        str(source.relative_to(SOURCE)) for source, mirror in _mirrors() if not mirror.exists()
    ]
    assert missing == []


def test_mirrored_unit_tests_define_tests():
    """Every mirror outside ``PLACEHOLDERS`` defines at least one test function."""
    empty = [
        str(mirror.relative_to(UNIT_TESTS))
        for _, mirror in _mirrors()
        if mirror.exists()
        and str(mirror.relative_to(UNIT_TESTS)) not in PLACEHOLDERS
        and not _defines_test(mirror)
    ]
    assert empty == []


def test_placeholders_are_existing_mirrors():
    """``PLACEHOLDERS`` names only real mirror files, so a typo cannot hide a source file."""
    mirrors = {str(mirror.relative_to(UNIT_TESTS)) for _, mirror in _mirrors()}
    assert PLACEHOLDERS <= mirrors
