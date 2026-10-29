"""Context-local global numerical and display settings."""

from contextvars import ContextVar

import numpy as np

from gemini.core.types.fluid import BRINE, Fluid
from gemini.utils.context import ContextSetting

_state = ContextVar(
    "gemini_runtime_state",
    default={"precision": "float64", "display_units": "si", "default_fluid": BRINE},
)


def state():
    """Return a copy of the current runtime settings."""
    result = _state.get().copy()
    result["default_fluid"] = result["default_fluid"].model_dump(mode="json")
    return result


def load_state(values):
    """Replace runtime settings from a checkpoint-safe dictionary."""
    values = dict(values)
    values["default_fluid"] = Fluid.model_validate(values.get("default_fluid", BRINE))
    _validate(values.get("precision", "float64"), values.get("display_units", "si"))
    _state.set(values)


def _validate(precision, display_units):
    if precision not in {"float64", "float32"}:
        raise ValueError("precision must be 'float64' or 'float32'")
    if display_units not in {"si", "field"}:
        raise ValueError("display_units must be 'si' or 'field'")


def set_default_fluid(fluid):
    """Set the default immutable fluid for newly constructed modules and streams."""
    _state.set(_state.get() | {"default_fluid": Fluid.model_validate(fluid)})


def get_default_fluid():
    """Return the context-local default fluid."""
    return _state.get()["default_fluid"]


def set_precision(precision):
    """Select float64 or legacy-compatible float32 correlation arithmetic."""
    _validate(precision, get_display_units())
    _state.set(_state.get() | {"precision": precision})


def get_precision():
    """Return the configured numerical precision name."""
    return _state.get()["precision"]


def dtype():
    """Return the NumPy dtype selected by the runtime."""
    return np.float32 if get_precision() == "float32" else np.float64


def set_display_units(display_units):
    """Select SI or compact field units for representation only."""
    _validate(get_precision(), display_units)
    _state.set(_state.get() | {"display_units": display_units})


def get_display_units():
    """Return the display-unit system."""
    return _state.get()["display_units"]


def manual_seed(seed):
    """Seed NumPy's process-local random generator."""
    np.random.seed(seed)


def settings(**changes):
    """Apply settings inside a ``with`` block or a decorated function, then restore them.

    Changes are validated and merged into the settings current at entry.
    """

    def update(current):
        updated = current | changes
        if "default_fluid" in changes:
            updated["default_fluid"] = Fluid.model_validate(changes["default_fluid"])
        _validate(updated["precision"], updated["display_units"])
        return updated

    return ContextSetting(_state, update)
