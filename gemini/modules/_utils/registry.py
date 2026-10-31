"""The one registry of module and plant types: stable names, categories and how to get each.

A module class registers under its class name and its ``category``: for a shipped class the folder
that holds it (``Module.category``), for a class from outside the value it states. A plant that
exists as a spec registers under its name with a ``build`` function that returns a new plant. Both
kinds share one table, so a plant spec can name any of them as the ``type`` of a child.
"""

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gemini.errors import ValidationError
from gemini.modules.module import Module
from gemini.utils.strings import close_matches, did_you_mean, join_names

CATEGORIES = (
    "subsurface",
    "wells",
    "pumps",
    "treatment",
    "exchangers",
    "heating",
    "cooling",
    "power",
    "storage",
    "piping",
    "grids",
    "environment",
    "control",
    "plants",
)
"""Every module category, in display order: the folders of ``gemini/modules``."""


@dataclass(frozen=True)
class _Entry:
    """One registered type: a module class, or the function that builds a spec plant."""

    category: str
    module: type[Module] | None = None
    build: Any = None


_entries = {}


def _check_category(name, category):
    if category not in CATEGORIES:
        raise ValidationError(
            f"modules.register: {name}.category = {category!r}; expected one of "
            f"{join_names(CATEGORIES)}{did_you_mean(category, CATEGORIES)}",
            path=name,
            suggestions=close_matches(category, CATEGORIES),
        )


def register(cls):
    """Add a ``Module`` class under its class name and return it, so it can join a plant.

    A class from outside states ``category``, one of the fixed list. Registering the same class
    again does nothing; another class of that name is refused.
    """
    if not (isinstance(cls, type) and issubclass(cls, Module)):
        raise ValidationError(f"modules.register: cls = {cls!r}; expected a Module class")
    name = cls.__name__
    _check_category(name, cls.category)
    existing = _entries.get(name)
    if existing is not None and existing.module is not cls:
        raise ValidationError(f"modules.register: name {name!r} is already taken", path=name)
    _entries[name] = _Entry(cls.category, module=cls)
    return cls


def register_plant(name, build):
    """Add a spec plant under ``name``; ``build()`` returns a new plant without values."""
    if name in _entries:
        raise ValidationError(f"plants.register: name {name!r} is already taken", path=name)
    _entries[name] = _Entry("plants", build=build)


def names(category=None):
    """Return the registered names, sorted, of every category or of one."""
    if category is not None:
        _check_category("names", category)
    return sorted(name for name, entry in _entries.items() if category in (None, entry.category))


def categories():
    """Return the fixed category list."""
    return list(CATEGORIES)


def category(name):
    """Return the category of a registered name."""
    return _entry(name).category


def _entry(name):
    entry = _entries.get(name)
    if entry is None:
        raise ValidationError(
            f"modules: unknown module type {name!r}{did_you_mean(name, _entries)}",
            path=name,
            suggestions=close_matches(name, _entries),
            code="unknown_name",
        )
    return entry


def get(name):
    """Return the class registered as ``name``, or a new plant for a spec plant.

    Both answer ``describe()``, ``parameter_schema()`` and ``validate_params(params)``.
    """
    entry = _entry(name)
    return entry.module if entry.module is not None else entry.build()


def _import_file(path):
    """Import the Python file at ``path`` as a module of its own and return it."""
    file = Path(path)
    if not file.is_file():
        raise ValidationError(f"modules.load_file: path = {str(path)!r}; expected a Python file")
    name = f"gemini_loaded_{file.stem}"
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        del sys.modules[name]
        raise ValidationError(
            f"modules.load_file: path = {str(path)!r}; importing it raised "
            f"{type(error).__name__}: {error}",
            path=str(path),
            code="invalid_format",
        ) from error
    return module


def load_file(path):
    """Import the Python file at ``path``, register its ``Module`` classes and return their names.

    The file is executed, so load only code that is meant to run. Every class the file defines
    that derives from ``Module`` and states a ``category`` is registered with ``register``, in the
    order of definition, so a plant spec can name it as a ``type``; a base class without a
    category is left out. A name is registered once per process: loading another class of an
    already registered name raises ``ValidationError``.

    Parameters
    ----------
    path : str or Path
        A Python source file.

    Returns
    -------
    list of str
        The registered class names.

    Raises
    ------
    ValidationError
        The path is not a file (code ``invalid_value``), executing it raised an error (code
        ``invalid_format``, the message names the error), or it defines no module class that
        states a category.
    """
    module = _import_file(path)
    classes = [
        item
        for item in vars(module).values()
        if isinstance(item, type)
        and issubclass(item, Module)
        and item.__module__ == module.__name__
        and item.category is not None
    ]
    if not classes:
        raise ValidationError(
            f"modules.load_file: path = {str(path)!r}; expected the file to define a Module "
            "class that states a category",
            path=str(path),
        )
    return [register(item).__name__ for item in classes]
