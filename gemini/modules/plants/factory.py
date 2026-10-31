"""Make the module a spec or a call to ``Plant.add`` names: a registry type or a group."""

from gemini.errors import ValidationError
from gemini.modules._utils import registry
from gemini.modules._utils.container import ModuleDict, ModuleList

GROUPS = {"ModuleDict": ModuleDict, "ModuleList": ModuleList}


def make_module(kind):
    """Return ``(module, registered name)`` for a registry name, a group name or a class."""
    if isinstance(kind, str) and kind in GROUPS:
        return GROUPS[kind](), kind
    name = kind if isinstance(kind, str) else getattr(kind, "__name__", repr(kind))
    try:
        found = registry.get(name)
    except ValidationError as error:
        raise ValidationError(
            str(error), path="type", suggestions=error.suggestions, code=error.code
        ) from error
    if not isinstance(kind, str) and found is not kind:
        raise ValidationError(
            f"add: type = {kind!r}; register the class with gm.modules.register first",
            code="invalid_value",
        )
    return (found() if isinstance(found, type) else found), name
