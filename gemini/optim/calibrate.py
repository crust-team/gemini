"""Bounded calibration using only Engine.replay for model predictions."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from gemini.core.engine.engine import Engine
from gemini.core.modules.heat import HeatExchanger
from gemini.core.modules.pumps import ESP
from gemini.core.physics import heat_transfer
from gemini.core.physics.units import to_si
from gemini.errors import BindingError, ConfigurationError, InsufficientDataError
from gemini.utils.strings import join_names, join_path

_MASS_FLOW_UNITS = {"kg/s", "t/h"}
"""Mass-flow units ``units.to_si`` accepts; other flow units are volume flows."""

_FIT_TARGETS = [
    (HeatExchanger, ("ua",), {"duty", "hot_out_T", "cold_out_T"}),
    (ESP, ("head_coeff",), {"head", "discharge_pressure"}),
    (ESP, None, {"power", "head", "discharge_pressure"}),
]
"""Measured outputs fitted per module class and parameter set (``None``: any parameters)."""


@dataclass(frozen=True)
class CalibrationResult:
    """Initial/fitted design values, normalised RMS per output and optimizer diagnostics."""

    fitted: dict[str, Any]
    rms_before: float
    rms_after: float
    observations: int
    success: bool
    message: str
    applied: bool
    initial: dict[str, Any]
    rms_by_output_before: dict[str, float]
    rms_by_output_after: dict[str, float]
    evaluations: int

    def __repr__(self):
        """Show the fitted change and its measured residual improvement."""
        values = ", ".join(
            f"{key}: {self.initial[key]} -> {value}" for key, value in self.fitted.items()
        )
        return (
            f"CalibrationResult({values}; RMS {self.rms_before:.6g} -> {self.rms_after:.6g}; "
            f"evaluations={self.evaluations}, success={self.success}, applied={self.applied})"
        )


@dataclass(frozen=True)
class _Coordinates:
    """Optimiser coordinates: every fitted value divided by its initial magnitude.

    ``sizes`` maps each field to its value count and whether it is a list parameter.
    """

    sizes: dict[str, tuple[int, bool]]
    scale: np.ndarray
    initial: np.ndarray
    lower: np.ndarray
    upper: np.ndarray

    def unpack(self, x):
        """Return parameter values for coordinates ``x``."""
        values, offset = {}, 0
        for key, (size, is_vector) in self.sizes.items():
            part = (x[offset : offset + size] * self.scale[offset : offset + size]).tolist()
            values[key] = part if is_vector else part[0]
            offset += size
        return values


def _owner(plant, params):
    """Return the one module owning ``params``, its plant path and the parameter names."""
    if not params:
        raise ValueError("calibrate: params = []; expected at least one Parameter")
    for parameter in params:
        if not parameter.calibratable:
            raise ConfigurationError(
                f"{parameter.path}: calibratable = False; expected parameters declared with "
                "calibratable=True"
            )
    owners = {parameter.owner for parameter in params}
    if len(owners) != 1:
        paths = sorted(owner.path for owner in owners)
        raise ConfigurationError(
            f"calibrate: parameter owners = {join_names(paths)}; expected one module at a time"
        )
    module = owners.pop()
    path = next((path for path, item in plant.named_modules() if item is module), None)
    if path is None:
        raise ConfigurationError(f"{module.path}: module is not part of the supplied plant")
    fields = [parameter.name for parameter in params]
    duplicates = sorted({field for field in fields if fields.count(field) > 1})
    if duplicates:
        raise ConfigurationError(
            f"{join_path(path, duplicates[0])}: parameter given twice; expected each once"
        )
    return module, path, fields


def _check_single_snapshot(module, path, index):
    """Reject windows that start before every dated snapshot or span a snapshot change."""
    start, end = index[0], index[-1]
    dates = [item.valid_from for item in module.param_history]
    if all(date is not None and date > start for date in dates):
        first = min(dates, default=None)
        raise ConfigurationError(
            f"{path}: calibration window starts {start}; first parameter snapshot valid_from = "
            f"{first}; expected a window inside one dated design snapshot"
        )
    changes = sorted(date for date in dates if date is not None and start < date <= end)
    if changes:
        raise ConfigurationError(
            f"{path}: parameter snapshots start at {changes[0]} inside the calibration window "
            f"{start} to {end}; expected one dated design snapshot"
        )


def _fit_targets(module, path, measured, fields):
    """Return the sorted measured outputs to fit for this module and parameter set."""
    targets = set(module.outputs(recurse=False)) & measured.keys()
    for module_class, target_fields, allowed in _FIT_TARGETS:
        if isinstance(module, module_class) and target_fields in (None, tuple(fields)):
            targets &= allowed
            break
    if not targets:
        raise BindingError(
            f"{path}: measured bindings = {join_names(sorted(measured))}; expected at least one "
            f"output of {join_names(sorted(module.outputs(recurse=False)))}"
        )
    return sorted(targets)


def _bounds(bounds):
    """Return closed ``(lower, upper)`` limits of a parameter's ge/gt/le/lt bounds."""
    low = bounds.get("ge", bounds.get("gt", -np.inf))
    high = bounds.get("le", bounds.get("lt", np.inf))
    if "gt" in bounds:
        low = np.nextafter(low, np.inf)
    if "lt" in bounds:
        high = np.nextafter(high, -np.inf)
    return low, high


def _coordinates(module, path, fields):
    """Return scaled coordinates starting at the module's current parameter values.

    Each value is scaled by its magnitude (at least 1e-30), and zero values by 1.
    """
    sizes, scale, initial, lower, upper = {}, [], [], [], []
    for field in fields:
        value = getattr(module, field)
        if value is None or isinstance(value, bool):
            raise ConfigurationError(f"{path}.{field} = {value!r}; expected a numeric value")
        values = np.atleast_1d(np.asarray(value, dtype=float))
        sizes[field] = (len(values), isinstance(value, (list, tuple)))
        field_scale = np.where(values == 0, 1.0, np.maximum(np.abs(values), 1e-30))
        low, high = _bounds(module.get_parameter(field).bounds)
        scale.extend(field_scale)
        initial.extend(values / field_scale)
        lower.extend(np.full(len(values), low) / field_scale)
        upper.extend(np.full(len(values), high) / field_scale)
    return _Coordinates(sizes, *map(np.asarray, (scale, initial, lower, upper)))


@dataclass(frozen=True)
class _Observed:
    """Observations bound to the calibrated module; a dataset column unit wins over the binding."""

    dataset: Any
    data: Any
    bindings: Any

    def unit(self, binding):
        """Return the unit of a bound column; dataset metadata wins over the binding."""
        return self.dataset.unit(binding.column, binding.unit)

    def values(self, binding):
        """Return a bound column converted to SI."""
        unit = self.unit(binding)
        return np.array([to_si(value, unit) for value in self.data[binding.column]])


def _ua_guess(module, observed, measured, valid):
    """Return the median apparent UA [W/K] of the valid rows, or ``None`` if none is defined.

    Each row gives ``duty / LMTD`` with temperature differences clipped at zero.
    """
    inlets = observed.bindings.inlets
    hot_in = observed.values(inlets["hot_in"]["T"])[valid]
    cold_in = observed.values(inlets["cold_in"]["T"])[valid]
    hot_out, cold_out = measured["hot_out_T"][valid], measured["cold_out_T"][valid]
    if module.arrangement == "counterflow":
        differences = zip(hot_in - cold_out, hot_out - cold_in)
    else:
        differences = zip(hot_in - cold_in, hot_out - cold_out)
    apparent = [
        duty / delta
        for duty, pair in zip(measured["duty"][valid], differences)
        if (delta := heat_transfer.lmtd(max(0, pair[0]), max(0, pair[1]))) > 0
    ]
    return [np.median(apparent)] if apparent else None


def _head_coefficient_guess(module, path, observed, measured, valid):
    """Return head coefficients fitted to the valid rows, or ``None`` without head data.

    Mass flows are converted to volume flows at the measured suction conditions.
    """
    if "head" not in measured:
        return None
    suction = observed.bindings.inlets["suction"]
    flows = observed.values(suction["m_dot"])
    if observed.unit(suction["m_dot"]) in _MASS_FLOW_UNITS:
        pressures, temperatures = observed.values(suction["p"]), observed.values(suction["T"])
        flows /= np.array(
            [module.fluid.properties(p, t).density for p, t in zip(pressures, temperatures)]
        )
    distinct = len(np.unique(flows[valid]))
    if distinct < 6:
        raise InsufficientDataError(
            f"{path}.head_coeff: distinct valid flows = {distinct}; expected at least 6 to seed "
            "the head-curve guess"
        )
    frequencies = observed.values(observed.bindings.controls["frequency"])[valid]
    return module.fit_head_coefficients(
        flows[valid], frequencies, measured["head"][valid], module.no_stages
    )


def _initial_guess(module, path, fields, observed, measured, valid):
    """Return an equipment-specific starting value for the fitted parameters, or ``None``."""
    if isinstance(module, HeatExchanger) and fields == ["ua"]:
        return _ua_guess(module, observed, measured, valid)
    if isinstance(module, ESP) and fields == ["head_coeff"]:
        return _head_coefficient_guess(module, path, observed, measured, valid)
    return None


def _predictor(runner, trial, dataset, index, path, targets, coordinates):
    """Return ``predict(x)``: replayed targets [SI] for coordinates ``x``, one row per tick."""
    target = trial.get_submodule(path)

    def predict(x):
        target.update_params(**coordinates.unpack(x))
        predictions = runner.replay(trial, dataset, only=[path]).to_frame()
        if path not in predictions.columns.get_level_values(0):
            raise InsufficientDataError(f"{path}: module was skipped on every calibration row")
        return predictions[path].reindex(index)[targets].to_numpy(dtype=float)

    return predict


def _valid_rows(predicted, measured, path):
    """Return the rows where every target is both predicted and measured."""
    valid = np.isfinite(predicted).all(axis=1) & np.isfinite(measured).all(axis=1)
    if not valid.any():
        raise InsufficientDataError(f"{path}: no row has every target measured and predicted")
    return valid


def _rms(values, axis=None):
    return np.sqrt(np.mean(values**2, axis=axis))


def _fit(residual, start, coordinates):
    """Run the bounded least-squares fit: at most 200 evaluations, all tolerances 1e-10."""
    return least_squares(
        residual,
        start,
        bounds=(coordinates.lower, coordinates.upper),
        x_scale="jac",
        max_nfev=200,
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
    )


def _result(fitted, values, initial, targets, errors_before, errors_after, applied):
    """Summarise a fit; errors are scaled residuals with one column per target."""
    return CalibrationResult(
        fitted=values,
        rms_before=float(_rms(errors_before)),
        rms_after=float(_rms(errors_after)),
        observations=len(errors_before),
        success=bool(fitted.success),
        message=fitted.message,
        applied=applied,
        initial=initial,
        rms_by_output_before=dict(zip(targets, _rms(errors_before, axis=0).tolist())),
        rms_by_output_after=dict(zip(targets, _rms(errors_after, axis=0).tolist())),
        evaluations=fitted.nfev,
    )


def calibrate(plant, dataset, params, start=None, end=None, engine=None, apply=True):
    """Fit measured outputs with bounded least squares through the public replay API.

    With apply=True, successful fits replace current parameters and persist as explicit
    overrides. No dated history entry is added. apply=False leaves the plant unchanged.
    Windows must lie in one design snapshot; holdout observations never enter the objective.
    The rows fitted are those where every target is measured and predicted at the initial
    values; equipment-specific starting guesses use the same rows.
    """
    original, path, fields = _owner(plant, params)
    dataset = dataset.window(start, end)
    data = dataset.read()
    if not len(data):
        raise InsufficientDataError(f"{path}: calibration window {start} to {end} has no rows")
    _check_single_snapshot(original, path, data.index)
    trial = deepcopy(plant)
    target = trial.get_submodule(path)
    target.update_params(**original.params_at(data.index[0]))
    observed = _Observed(dataset, data, plant.bindings[path])
    targets = _fit_targets(original, path, observed.bindings.measured, fields)
    measured = {name: observed.values(observed.bindings.measured[name]) for name in targets}
    matrix = np.column_stack([measured[name] for name in targets])
    scales = np.maximum(np.nanmedian(abs(matrix), axis=0), 1e-12)
    initial = {field: getattr(target, field) for field in fields}
    coordinates = _coordinates(target, path, fields)
    runner = engine if engine is not None else Engine(on_error="raise")
    predict = _predictor(runner, trial, dataset, data.index, path, targets, coordinates)
    before = predict(coordinates.initial)
    valid = _valid_rows(before, matrix, path)

    def residual(x):
        return ((predict(x)[valid] - matrix[valid]) / scales).ravel()

    guess = _initial_guess(target, path, fields, observed, measured, valid)
    start_x = coordinates.initial if guess is None else np.asarray(guess) / coordinates.scale
    fitted = _fit(residual, start_x, coordinates)
    errors_before = (before[valid] - matrix[valid]) / scales
    errors_after = residual(fitted.x).reshape(-1, len(targets))
    values = coordinates.unpack(fitted.x)
    applied = bool(apply and fitted.success)
    if applied:
        original.update_params(**values)
    return _result(fitted, values, initial, targets, errors_before, errors_after, applied)
