"""Make the module a spec or a call to ``Plant.add`` names: a registry type or a group."""

from gemini.errors import ValidationError
from gemini.modules._utils import registry
from gemini.modules._utils.container import ModuleDict, ModuleList

GROUPS = {"ModuleDict": ModuleDict, "ModuleList": ModuleList}


def make_module(type_name):
    """Return ``(module, registered name)`` for a registry name, a group name or a class."""
    if isinstance(type_name, str) and type_name in GROUPS:
        return GROUPS[type_name](), type_name
    name = (
        type_name if isinstance(type_name, str) else getattr(type_name, "__name__", repr(type_name))
    )
    try:
        found = registry.get(name)
    except ValidationError as error:
        raise ValidationError(
            str(error), path="type", suggestions=error.suggestions, code=error.code
        ) from error
    if not isinstance(type_name, str) and found is not type_name:
        raise ValidationError(
            f"add: type = {type_name!r}; register the class with gm.modules.register first",
            code="invalid_value",
        )
    return (found() if isinstance(found, type) else found), name
