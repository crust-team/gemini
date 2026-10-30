"""Context-local numerical and display settings.

Settings live in a ``contextvars.ContextVar``: a change applies to the current context only.
New threads start from the defaults; code that hands work to threads passes ``state()`` along
or runs it in ``contextvars.copy_context()``.
"""

from contextvars import ContextVar

from gemini.errors import ValidationError
from gemini.types.fluid import BRINE, Fluid
from gemini.utils.context import ContextSetting
from gemini.utils.strings import did_you_mean, join_names

__all__ = [
    "settings",
    "state",
    "load_state",
    "get_default_fluid",
    "set_default_fluid",
    "get_precision",
    "set_precision",
    "get_display_units",
    "set_display_units",
]

_DEFAULTS = {"precision": "float64", "display_units": "si", "default_fluid": BRINE}
_CHOICES = {"precision": ("float64", "float32"), "display_units": ("si", "field")}

_state = ContextVar("gemini_runtime_state", default=_DEFAULTS)


def _check_names(names, required=False):
    """Reject unknown setting names and, if ``required``, missing ones."""
    for name in names:
        if name not in _DEFAULTS:
            raise ValidationError(
                f"runtime: setting {name!r} is unknown; expected one of "
                f"{join_names(_DEFAULTS)}{did_you_mean(name, _DEFAULTS)}",
                code="unknown_name",
            )
    missing = [name for name in _DEFAULTS if name not in names]
    if required and missing:
        raise ValidationError(
            f"runtime: state is missing {join_names(missing)}; expected every setting",
            code="unknown_name",
        )


def _validated(values):
    """Return complete settings with a validated fluid; reject values outside the choices."""
    for name, choices in _CHOICES.items():
        if values[name] not in choices:
            raise ValidationError(
                f"runtime: {name} = {values[name]!r}; expected one of {join_names(choices)}",
                code="unknown_name",
            )
    return values | {"default_fluid": Fluid.model_validate(values["default_fluid"])}


def state():
    """Return a copy of the current runtime settings."""
    result = _state.get().copy()
    result["default_fluid"] = result["default_fluid"].model_dump(mode="json")
    return result


def load_state(values):
    """Replace runtime settings from a complete dictionary returned by ``state()``."""
    _check_names(values, required=True)
    _state.set(_validated(dict(values)))


def _update(**changes):
    _check_names(changes)
    _state.set(_validated(_state.get() | changes))


def set_default_fluid(fluid):
    """Set the default immutable fluid for newly constructed modules and streams."""
    _update(default_fluid=fluid)


def get_default_fluid():
    """Return the context-local default fluid."""
    return _state.get()["default_fluid"]


def set_precision(precision):
    """Select float64 or legacy-compatible float32 correlation arithmetic."""
    _update(precision=precision)


def get_precision():
    """Return the configured numerical precision name."""
    return _state.get()["precision"]


def set_display_units(display_units):
    """Select SI or compact field units for representation only."""
    _update(display_units=display_units)


def get_display_units():
    """Return the display-unit system."""
    return _state.get()["display_units"]


def settings(**changes):
    """Apply settings inside a ``with`` block or a decorated function, then restore them.

    Unknown names are rejected at once; values are validated and merged into the settings
    current at entry.
    """
    _check_names(changes)
    return ContextSetting(_state, lambda current: _validated(current | changes))
