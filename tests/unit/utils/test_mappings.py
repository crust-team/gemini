"""Read-only attribute mappings and nested dictionary lookups."""

import pytest

from gemini.utils.mappings import AttributeMapping, get_nested, set_nested


class Named(AttributeMapping):
    """Mapping with a descriptive unknown-key message."""

    def _unknown(self, name):
        return f"unknown {name!r}"


def test_attribute_mapping_reads_by_key_and_attribute():
    """Values keep insertion order and both access forms agree."""
    values = AttributeMapping({"b": 2, "a": 1})
    assert list(values) == ["b", "a"]
    assert values["a"] == values.a == 1
    assert len(values) == 2
    assert repr(values) == "{'b': 2, 'a': 1}"
    assert dict(values) == {"b": 2, "a": 1}


def test_unknown_keys_raise_the_described_error():
    """Item access raises KeyError and attribute access AttributeError with one message."""
    with pytest.raises(KeyError, match="missing"):
        AttributeMapping({})["missing"]
    with pytest.raises(KeyError, match="unknown 'x'"):
        Named({})["x"]
    with pytest.raises(AttributeError, match="unknown 'x'"):
        Named({}).x


def test_membership_does_not_describe_unknown_keys():
    """``in`` answers from the keys alone, without building an unknown-key message."""

    class Counting(AttributeMapping):
        described = []

        def _unknown(self, name):
            self.described.append(name)
            return name

    values = Counting({"a": 1})
    assert "a" in values
    assert "b" not in values
    assert Counting.described == []


def test_nested_get_and_set():
    """Nested lookups fall back to a default; nested sets create intermediate dicts."""
    data = {"stream_defaults": {"esp": {"suction": {"T": 300.0}}}}
    assert get_nested(data, ["stream_defaults", "esp", "suction"]) == {"T": 300.0}
    assert get_nested(data, ["stream_defaults", "filter"], {}) == {}
    set_nested(data, ["root_inputs", "secondary", "T"], 330.0)
    assert data["root_inputs"] == {"secondary": {"T": 330.0}}


def test_subclasses_choose_the_error_classes():
    """One error class deriving from both built-ins serves item and attribute access."""

    class Missing(KeyError, AttributeError):
        """Lookup error for both access forms."""

    class Strict(Named):
        key_error = Missing
        attribute_error = Missing

    with pytest.raises(Missing):
        Strict({})["x"]
    with pytest.raises(Missing):
        Strict({}).x
