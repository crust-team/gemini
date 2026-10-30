"""The generated schemas and samples of ``docs/schemas`` are up to date."""

import json
from pathlib import Path

import pytest

from scripts import write_schemas
from tests.fixtures.json_schema import check
from tests.fixtures.parity import RTOL

SCHEMAS = Path(write_schemas.__file__).parents[1] / "docs" / "schemas"
DOCUMENTS = (
    "module_description",
    "plant_spec",
    "results_summary",
    "problem",
    "value",
    "check",
    "profile",
)


def same(first, second):
    """Return whether two JSON documents are equal, numbers within the documented tolerance."""
    if isinstance(first, dict) and isinstance(second, dict):
        keys_match = first.keys() == second.keys()
        return keys_match and all(same(first[key], second[key]) for key in first)
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(map(same, first, second))
    if isinstance(first, float) and isinstance(second, float):
        return abs(first - second) <= RTOL * max(abs(first), abs(second))
    return first == second


@pytest.fixture(scope="module")
def documents():
    """Generate every document once."""
    return json.loads(json.dumps(write_schemas.documents()))


def test_generated_files_are_up_to_date(documents):
    """Stale samples mislead the other repositories."""
    for name, document in documents.items():
        assert same(document, json.loads((SCHEMAS / name).read_text())), name


@pytest.mark.parametrize("name", DOCUMENTS)
def test_every_sample_fits_its_schema(name):
    """Each exchanged document has a schema and a real sample."""
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    sample = json.loads((SCHEMAS / f"{name}.sample.json").read_text())
    assert check(sample, schema) == []


def test_the_checker_finds_problems():
    """A checker that accepts everything proves nothing."""
    schema = json.loads((SCHEMAS / "problem.schema.json").read_text())
    problems = check({"class": 1, "extra": 2}, schema)
    assert "$: unexpected extra" in problems and "$: missing message" in problems
