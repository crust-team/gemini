"""Enforce one mirrored unit-test module for every implementation file with logic."""

from pathlib import Path


def test_source_files_have_mirrored_unit_tests():
    """Keep the source-to-unit-test navigation rule mechanically enforced."""
    root = Path(__file__).parents[2]
    missing = []
    for source in (root / "gemini").rglob("*.py"):
        if source.name == "__init__.py":
            continue
        relative = source.relative_to(root / "gemini")
        expected = root / "tests/unit" / relative.parent / f"test_{relative.name}"
        if not expected.exists():
            missing.append(str(relative))
    assert missing == []
