"""One registry of module and plant types."""

import inspect
import sys
from pathlib import Path

import pytest

import gemini as gm
from gemini.errors import ValidationError
from gemini.modules._utils import registry
from gemini.modules.module import Module
from tests.fixtures.errors import raises


def test_every_registered_type_has_a_listed_category():
    """A name per module, a category from the fixed list."""
    assert "ESP" in gm.modules.names("pumps") and "ESP" not in gm.modules.names("heating")
    for name in gm.modules.names():
        assert registry.category(name) in gm.modules.categories()


def test_every_registered_type_has_the_category_of_its_folder():
    """A category is the folder of the class; a spec plant, of class ``Plant``, is ``plants``."""
    for name in gm.modules.names():
        item = gm.modules.get(name)
        cls = item if isinstance(item, type) else type(item)
        folder = Path(inspect.getfile(cls)).parent.name
        assert registry.category(name) == ("plants" if cls is gm.Plant else folder), name


def test_the_folders_are_the_categories_and_none_is_empty():
    """Every category has its folder and at least one module, and no folder is left over."""
    package = Path(registry.__file__).parents[1]
    folders = {path.parent.name for path in package.glob("[!_]*/__init__.py")}
    assert folders == set(gm.modules.categories())
    assert all(gm.modules.names(category) for category in gm.modules.categories())


def _subclasses(cls):
    for item in cls.__subclasses__():
        yield item
        yield from _subclasses(item)


def test_no_shipped_class_states_a_category():
    """The folder is the only source, so a class and its folder can never disagree."""
    shipped = [item for item in _subclasses(Module) if item.__module__.startswith("gemini.")]
    assert gm.modules.ESP in shipped
    assert [item for item in shipped if "category" in vars(item)] == []


@pytest.mark.parametrize(
    "name,category",
    [
        ("PIDController", "control"),
        ("FlashTurbine", "power"),
        ("ORC", "power"),
        ("Separator", "power"),
        ("AquiferStorage", "storage"),
        ("ProductionWell", "wells"),
        ("Cooler", "exchangers"),
        ("ElectricityGrid", "grids"),
        ("GasMakeup", "piping"),
        ("CHP", "heating"),
        ("AdsorptionChiller", "cooling"),
        ("Doublet", "plants"),
        ("ATESPlant", "plants"),
    ],
)
def test_the_category_of_a_module(name, category):
    """The modules that used to sit under a neighbouring category, and the plants."""
    assert registry.category(name) == category


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
    with raises(ValidationError, "unknown_name", match="did you mean 'Boiler'") as caught:
        gm.modules.get("Boilr")
    assert caught.value.to_dict()["suggestions"] == ["Boiler"]


def test_an_unknown_category_is_refused():
    """Only the fixed categories exist."""
    with pytest.raises(ValidationError, match="expected one of"):
        gm.modules.names("pump")


def test_a_class_needs_a_listed_category():
    """A module without a category cannot join the catalogue."""

    class NoCategory(Module):
        """Module without a category."""

    with pytest.raises(ValidationError, match="NoCategory.category"):
        registry.register(NoCategory)


def test_a_class_from_outside_states_its_own_category():
    """A subclass of a shipped class has no folder, so it does not inherit one."""

    class Mine(gm.modules.ESP):
        """Subclass that states nothing."""

    assert Mine.category is None and Mine().category is None
    with pytest.raises(ValidationError, match="Mine.category"):
        registry.register(Mine)


def test_a_taken_name_is_refused(monkeypatch):
    """Two classes never share a name; the same class registers twice without harm."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))

    class ESP(Module):
        """Second class of a taken name."""

        category = "pumps"

    with pytest.raises(ValidationError, match="already taken"):
        registry.register(ESP)
    assert registry.register(gm.modules.ESP) is gm.modules.ESP


def test_a_spec_plant_builds_a_new_plant_each_time(monkeypatch):
    """A plant entry is its build function."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))
    registry.register_plant("Example", lambda: gm.Plant("Example"))
    assert "Example" in gm.modules.names("plants")
    assert gm.modules.get("Example") is not gm.modules.get("Example")
    with pytest.raises(ValidationError, match="already taken"):
        registry.register_plant("Example", lambda: gm.Plant("Example"))


BOOSTER_FILE = Path(__file__).parents[3] / "fixtures" / "booster_module.py"


def test_load_file_registers_the_module_classes_of_a_file(monkeypatch):
    """The names come back in definition order and the class joins the catalogue."""
    monkeypatch.setattr(registry, "_entries", dict(registry._entries))
    assert gm.modules.load_file(BOOSTER_FILE) == ["Booster"]
    assert "Booster" in gm.modules.names("pumps")
    result = gm.evaluate("Booster", {}, {"fluid_in": {"m_dot": 10, "T": 300, "p": 2e5}}, {})
    assert result["outlets"]["fluid_out"]["p"]["value"] == pytest.approx(3e5)


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
