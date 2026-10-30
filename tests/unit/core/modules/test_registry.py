"""One registry of module and plant types."""

import sys
from pathlib import Path

import pytest

import gemini as gm
from gemini.core.modules import registry
from gemini.core.modules.module import Module
from gemini.errors import UnknownNameError, ValidationError


def test_every_registered_type_has_a_listed_category():
    """A name per module, a category from the fixed list."""
    assert "ESP" in gm.modules.names("pump") and "ESP" not in gm.modules.names("boiler")
    for name in gm.modules.names():
        assert registry.category(name) in gm.modules.categories()


def test_every_shipped_equipment_class_is_registered():
    """Nothing exported by ``gm.modules`` is missing from the catalogue."""
    exported = [getattr(gm.modules, name) for name in gm.modules.__all__]
    classes = [item for item in exported if isinstance(item, type) and issubclass(item, Module)]
    missing = [
        item.__name__
        for item in classes
        if item.category is not None and item.__name__ not in gm.modules.names()
    ]
    assert missing == []


def test_get_returns_the_class():
    """A module name gives its class."""
    assert gm.modules.get("ESP") is gm.modules.ESP


def test_an_unknown_name_suggests_close_ones():
    """The error carries the close names as data, for tool results."""
    with pytest.raises(UnknownNameError, match="did you mean 'Boiler'") as caught:
        gm.modules.get("Boilr")
    assert caught.value.to_dict()["suggestions"] == ["Boiler"]


def test_an_unknown_category_is_refused():
    """Only the fixed categories exist."""
    with pytest.raises(ValidationError, match="expected one of"):
        gm.modules.names("pumps")


def test_a_class_needs_a_listed_category():
    """A module without a category cannot join the catalogue."""

    class NoCategory(Module):
        """Module without a category."""

    with pytest.raises(ValidationError, match="NoCategory.category"):
        registry.register(NoCategory)


def test_a_taken_name_is_refused(monkeypatch):
    """Two classes never share a name; the same class registers twice without harm."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))

    class ESP(Module):
        """Second class of a taken name."""

        category = "pump"

    with pytest.raises(ValidationError, match="already taken"):
        registry.register(ESP)
    assert registry.register(gm.modules.ESP) is gm.modules.ESP


def test_a_spec_plant_builds_a_new_plant_each_time(monkeypatch):
    """A plant entry is its build function."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))
    registry.register_plant("Example", lambda: gm.Plant("Example"))
    assert "Example" in gm.modules.names("plant")
    assert gm.modules.get("Example") is not gm.modules.get("Example")
    with pytest.raises(ValidationError, match="already taken"):
        registry.register_plant("Example", lambda: gm.Plant("Example"))


BOOSTER_FILE = Path(__file__).parents[3] / "fixtures" / "booster_module.py"


def test_load_file_registers_the_module_classes_of_a_file(monkeypatch):
    """The names come back in definition order and the class joins the catalogue."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))
    assert gm.modules.load_file(BOOSTER_FILE) == ["Booster"]
    assert "Booster" in gm.modules.names("pump")
    result = gm.evaluate("Booster", {}, {"suction": {"m_dot": 10, "T": 300, "p": 2e5}}, {})
    assert result["outlets"]["discharge"]["p"]["value"] == pytest.approx(3e5)


def test_load_file_accepts_a_text_path_and_refuses_a_second_class_of_a_taken_name(monkeypatch):
    """Loading the same name from a changed file is a validation error, not a silent swap."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))
    gm.modules.load_file(str(BOOSTER_FILE))
    with pytest.raises(ValidationError, match="already taken"):
        gm.modules.load_file(BOOSTER_FILE)


@pytest.mark.parametrize(
    "source,code,message",
    [
        ("def broken(:\n", "invalid_format", "SyntaxError"),
        ("raise RuntimeError('boom')\n", "invalid_format", "boom"),
        ("VALUE = 1\n", "invalid_value", "define a Module class"),
    ],
)
def test_load_file_failures_are_validation_errors(tmp_path, monkeypatch, source, code, message):
    """A file that does not import, or defines nothing to register, is named in the error."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))
    file = tmp_path / "user_module.py"
    file.write_text(source)
    with pytest.raises(ValidationError, match=message) as error:
        gm.modules.load_file(file)
    assert error.value.code == code
    assert ("gemini_loaded_user_module" in sys.modules) == (code == "invalid_value")


def test_load_file_needs_an_existing_file(tmp_path):
    """A missing path is a validation error naming the path."""
    with pytest.raises(ValidationError, match="expected a Python file"):
        gm.modules.load_file(tmp_path / "missing.py")
