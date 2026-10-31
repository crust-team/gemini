"""One call of one module from plain JSON."""

from gemini.errors import GeminiError, ValidationError
from gemini.errors.base import check_on_error
from gemini.modules._utils import registry
from gemini.modules.module import Module
from gemini.types.flows import STREAM_FIELDS
from gemini.types.shapes import OutputUnits

STREAM_UNITS = {
    "m_dot": ("kg/s", "mass_flow"),
    "T": ("K", "temperature"),
    "p": ("Pa", "pressure"),
}
"""The SI unit and the quantity of each numeric stream field."""


def evaluate(module, parameters, inlets, controls, on_error="raise", units=None):
    """Return ``{outlets, outputs, errors}`` of one call of a registered module or class.

    ``module`` is a registry name or a ``Module`` class. ``parameters`` maps parameter names to
    numbers or unit strings (``"150 m3/h"``). ``inlets`` maps each inlet port to its stream
    fields, ``{"m_dot": "10 kg/s", "T": "80 degC", "p": "5 bar"}`` (or ``flow`` for a volume
    flow, and an optional ``fluid``). ``controls`` maps control and boundary names to values for
    this call only.

    The result is plain JSON with units: ``outlets`` is ``{port: {field: {value, unit}}}`` and
    ``outputs`` is ``{name: {value, unit}}``, in SI or in ``units``, a map from quantity to unit,
    and ``errors`` is empty. A call that fails raises; with ``on_error="record"`` it returns empty
    ``outlets`` and ``outputs`` and in ``errors`` the problem of what went wrong.
    """
    check_on_error(on_error)
    try:
        output = OutputUnits(units)
        instance = _instance(module)
        instance.update_params(**(parameters or {}))
        result = instance(dict(inlets or {}), **(controls or {}))
    except GeminiError as error:
        return _failed(error, on_error)
    except (TypeError, ValueError) as error:
        return _failed(ValidationError(str(error)), on_error)
    return {
        "outlets": _outlets(result.outlets, output),
        "outputs": _outputs(instance, result.outputs, output),
        "errors": [],
    }


def _instance(module):
    """Return a new module from a registry name or a class."""
    if isinstance(module, str):
        module = registry.get(module)
    if isinstance(module, Module):
        return module
    if not (isinstance(module, type) and issubclass(module, Module)):
        raise ValidationError(
            f"evaluate: module = {module!r}; expected a registry name or a Module class"
        )
    return module()


def _failed(error, on_error):
    """Raise the failure of a call, or return it under ``on_error="record"``."""
    if on_error == "raise":
        raise error
    return {"outlets": {}, "outputs": {}, "errors": [error.to_dict()]}


def _outlets(outlets, output):
    """Return each outlet stream as ``{field: {value, unit}}``."""
    return {
        port: {
            name: output.value(getattr(stream, name), *STREAM_UNITS[name]) for name in STREAM_FIELDS
        }
        for port, stream in outlets.items()
    }


def _outputs(instance, outputs, output):
    """Return each output as ``{value, unit}``; an output without a declared unit is ``"-"``."""
    declarations = instance.outputs(recurse=False)
    return {
        name: output.value(
            number,
            (declarations[name].unit if name in declarations else None) or "-",
            declarations[name].quantity if name in declarations else None,
        )
        for name, number in outputs.items()
    }
