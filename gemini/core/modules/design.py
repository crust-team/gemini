"""Dated parameters and bindings of a module tree, the one implementation behind ``Module``.

``Module.set_params``, ``params_at``, ``param_history``, ``bindable`` and ``set_bindings`` call
these functions with the module they belong to. Parameters are addressed by a module path below
that module and a (possibly dotted) parameter name; values are validated by their declarations,
so unit strings are accepted and stored in SI.
"""

from copy import deepcopy

from pydantic import ValidationError as PydanticError
from pydantic_core import to_jsonable_python

from gemini.core.physics import units
from gemini.core.types.bindings import DatedParams, ModuleBindings
from gemini.core.types.flows import STREAM_FIELDS
from gemini.errors import BindingError, ConfigurationError, UnitError, UnknownNameError
from gemini.utils.jsonable import to_plain
from gemini.utils.strings import close_matches, did_you_mean, join_names
from gemini.utils.time import EARLIEST, to_utc

FIELD_UNITS = {"m_dot": ("kg/s", "m3/s"), "T": ("K",), "p": ("Pa",)}
"""The SI units a column bound to a stream field may have; a volume flow becomes mass flow."""


def _date(item):
    return item.valid_from or EARLIEST


def snapshot_at(module, at):
    """Return the snapshot of ``module`` in force at ``at``; ``None`` selects the latest."""
    eligible = [
        item
        for item in module._param_history
        if at is None or item.valid_from is None or item.valid_from <= to_utc(at)
    ]
    if not eligible:
        raise ConfigurationError(f"{module.path}: no parameters valid at {at}")
    return max(eligible, key=_date)


def params_at(module, path, time=None):
    """Return the parameter values of the module at ``path`` in force at ``time`` as plain JSON."""
    values = module.get_module(path)._params_at(time)
    return to_plain(to_jsonable_python(values))


def param_history(module, path):
    """Return the dated snapshots of the module at ``path`` as ``[{valid_from, params}]``."""
    history = module.get_module(path)._param_history
    return to_plain([item.model_dump(mode="json") for item in history])


def parameter(module, name):
    """Return the parameter declaration ``name`` below ``module``; an unknown name suggests one."""
    declarations = {path: item for path, item in module.named_parameters()}
    if name not in declarations:
        raise UnknownNameError(
            f"{module.path}: unknown parameter {name!r}; valid: {join_names(declarations)}"
            f"{did_you_mean(name, declarations)}",
            suggestions=close_matches(name, declarations),
        )
    return declarations[name]


def _validated_changes(target, params):
    """Return ``{owner: {name: plain SI value}}`` for ``params``, raising before any change."""
    changes = {}
    for name, value in params.items():
        declaration = parameter(target, name)
        validated = declaration.validate(value)
        changes.setdefault(declaration.owner, {})[declaration.name] = to_jsonable_python(
            deepcopy(validated)
        )
    return changes


def _store_snapshot(owner, values, when):
    """Merge ``values`` into the snapshot dated ``when``, or add one built on the one in force."""
    history = owner._param_history
    entry = next((item for item in history if item.valid_from == when), None)
    if entry is not None:
        entry.params = entry.params | values
        return
    before = [
        item
        for item in history
        if when is None or item.valid_from is None or item.valid_from <= when
    ]
    reference = max(before, key=_date) if before else min(history, key=_date)
    history.append(DatedParams(valid_from=when, params=deepcopy(reference.params) | values))
    history.sort(key=_date)


def set_params(module, path, params, valid_from=None):
    """Store a validated, complete snapshot for the module at ``path`` and return ``module``.

    Each snapshot is the values in force at ``valid_from`` merged with ``params``. Without a
    date the undated base entry changes, and so do the current values.
    """
    when = None if valid_from is None else to_utc(valid_from)
    changes = _validated_changes(module.get_module(path), params)
    for owner, values in changes.items():
        _store_snapshot(owner, values, when)
        if when is None:
            for name, value in values.items():
                owner._parameters[name].set(value, explicit=False)
                owner._param_overrides.pop(name, None)
    return module


def bindable(module, path):
    """Return what the module at ``path`` accepts bindings for, by section."""
    target = module.get_module(path)
    return {
        "controls": list(target._controls),
        "boundaries": list(target._boundaries),
        "inlets": {port: list(STREAM_FIELDS) for port in target._inlets},
        "measured": list(target._outputs),
        "state": list(target._states),
    }


def _fits(unit, accepted):
    """Return whether ``unit`` converts to one of the SI units in ``accepted`` (``None``: any)."""
    return accepted is None or units.si_unit(unit) in accepted


def _check_name(section, name, valid):
    if name not in valid:
        raise UnknownNameError(
            f"{section}: unknown name {name!r}; valid: {join_names(valid)}"
            f"{did_you_mean(name, valid)}",
            path=f"{section}.{name}",
            suggestions=close_matches(name, valid),
        )


def _check_unit(path, binding, accepted):
    if not _fits(binding.unit, accepted):
        raise UnitError(
            f"{path}.unit: unit = {binding.unit!r}; expected a unit of {join_names(accepted)}",
            path=f"{path}.unit",
        )


def _accepted(declared, section):
    """Return the SI units a column may have for a declaration of unit ``declared``."""
    if not declared:
        return None
    volumetric = declared == "kg/s" and section in ("controls", "boundaries")
    return (declared, "m3/s") if volumetric else (declared,)


def _check_section(section, bound, declarations):
    for name, binding in bound.items():
        _check_name(section, name, declarations)
        _check_unit(f"{section}.{name}", binding, _accepted(declarations[name].unit, section))


def _check_inlets(bound, inlets):
    for port, fields in bound.items():
        _check_name("inlets", port, inlets)
        for field_name, binding in fields.items():
            _check_name(f"inlets.{port}", field_name, FIELD_UNITS)
            _check_unit(f"inlets.{port}.{field_name}", binding, FIELD_UNITS[field_name])


def _parsed_bindings(bindings):
    try:
        return ModuleBindings.model_validate(bindings)
    except PydanticError as error:
        raise BindingError(f"bindings: {error}") from error


def set_bindings(module, path, bindings):
    """Replace the bindings of the module at ``path``, checking names and units; return ``module``.

    ``bindings`` has the shape of ``ModuleBindings``: ``controls``, ``boundaries``, ``measured``
    and ``state`` map a name to ``{column, unit}`` and ``inlets`` maps a port to its fields. A
    binding whose unit does not convert to the unit of its declaration is refused.
    """
    target = module.get_module(path)
    parsed = _parsed_bindings(bindings)
    _check_section("controls", parsed.controls, target._controls)
    _check_section("boundaries", parsed.boundaries, target._boundaries)
    _check_section("measured", parsed.measured, target._outputs)
    _check_section("state", parsed.state, target._states)
    _check_inlets(parsed.inlets, target._inlets)
    if parsed == ModuleBindings():
        module.bindings.pop(path, None)
    else:
        module.bindings[path] = parsed
    return module
