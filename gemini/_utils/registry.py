"""The one registry of module and plant types: stable names, categories and how to get each.

``Module.__init_subclass__`` registers every class that has a ``category`` under its class name: for
a shipped class the folder that holds it (``Module.category``), for a class from outside the value
it states. A class whose own body says ``abstract = True`` is left out. Plant classes are in the
same table, so a plant dict can name any of them as the ``type`` of a child.
"""

from dataclasses import dataclass

from gemini._utils.strings import close_matches, did_you_mean, join_names
from gemini.errors import ValidationError

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
    """One registered type: a module class and its category."""

    category: str
    module: type


_entries = {}


def _check_category(name, category):
    if category not in CATEGORIES:
        raise ValidationError(
            f"modules: {name}.category = {category!r}; expected one of "
            f"{join_names(CATEGORIES)}{did_you_mean(category, CATEGORIES)}",
            path=name,
            suggestions=close_matches(category, CATEGORIES),
        )


def register(cls):
    """Add a ``Module`` class under its class name.

    A class from outside states ``category``, one of the fixed list. Importing the same class again
    replaces it; another class of that name is refused with code ``duplicate_name``.
    """
    name = cls.__name__
    _check_category(name, cls.category)
    existing = _entries.get(name)
    if existing is not None and _origin(existing.module) != _origin(cls):
        raise ValidationError(
            f"modules: {_origin(cls)} takes the name {name!r} of {_origin(existing.module)}; "
            "expected a name no other class has",
            path=name,
            code="duplicate_name",
        )
    _entries[name] = _Entry(cls.category, module=cls)


def _origin(cls):
    """Return where a class is defined, which is the same when its file is imported again."""
    return f"{cls.__module__}.{cls.__qualname__}"


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
    """Return the class registered as ``name``."""
    return _entry(name).module
