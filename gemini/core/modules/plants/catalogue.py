"""The plant catalogue: which plants exist and how to get one."""

from gemini.core.modules import registry
from gemini.errors import UnknownNameError
from gemini.utils.strings import close_matches, did_you_mean, join_names


def names():
    """Return the registry names of the plants, sorted: the spec plants and the special cases."""
    return registry.names("plant")


def get(name):
    """Return a new plant of registry name ``name`` whose parameters are not set.

    A spec plant comes back as a ``Plant`` and a special case as an instance of its class. An
    unknown name, or the name of a module that is not a plant, raises ``UnknownNameError`` with
    close matches in ``suggestions``.
    """
    valid = names()
    if name not in valid:
        raise UnknownNameError(
            f"plants.get: unknown plant {name!r}; valid: {join_names(valid)}"
            f"{did_you_mean(name, valid)}",
            path=name,
            suggestions=close_matches(name, valid),
        )
    found = registry.get(name)
    return found() if isinstance(found, type) else found
