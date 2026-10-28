"""Bounded calibration using only Engine.replay for model predictions."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from gemini.core.engine.engine import Engine
from gemini.core.physics import heat_transfer
from gemini.core.physics.units import to_si


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


def calibrate(plant, dataset, params, start=None, end=None, engine=None, apply=True):
    """Fit measured outputs with bounded least squares through the public replay API.

    With apply=True, successful fits replace current parameters and persist as explicit
    overrides. No dated history entry is added. apply=False leaves the plant unchanged.
    Windows must lie in one design snapshot; holdout observations never enter the objective.
    """
    if not params:
        raise ValueError("params must contain at least one Parameter")
    if any(not parameter.calibratable for parameter in params):
        raise ValueError("All calibration parameters must declare calibratable=True")
    owners = {parameter.owner for parameter in params}
    if len(owners) != 1:
        raise ValueError("Calibrate parameters belonging to one module at a time")
    original = owners.pop()
    module_path = original._path
    fields = [parameter.name for parameter in params]
    dataset = dataset.window(start, end)
    data = dataset.read(dataset.start, dataset.end)
    if plant.get_submodule(module_path) is not original:
        raise ValueError("Calibration parameters must belong to the supplied plant")
    if not len(data):
        raise ValueError(f"{module_path}: no complete calibration observations")
    snapshots = {
        max(
            (p for p in original.param_history if p.valid_from is None or p.valid_from <= t),
            key=lambda p: p.valid_from.timestamp() if p.valid_from else -np.inf,
        ).valid_from
        for t in data.index
    }
    if len(snapshots) != 1:
        raise ValueError("Calibrate one dated design snapshot at a time")
    trial = deepcopy(plant)
    target = trial.get_submodule(module_path)
    target.update_params(**original.params_at(data.index[0]))
    bindings = plant.bindings[module_path]
    targets = set(original.outputs()) & bindings.measured.keys()
    if original.name == "heat_exchanger" and fields == ["ua"]:
        targets &= {"duty", "hot_out_T", "cold_out_T"}
    if original.name == "esp":
        targets &= (
            {"head", "discharge_pressure"}
            if fields == ["head_coeff"]
            else {"power", "head", "discharge_pressure"}
        )
    targets = sorted(targets)
    if not targets:
        raise ValueError(f"{module_path}: no measured outputs to fit")
    measured = np.column_stack(
        [
            [
                to_si(v, dataset.columns[b.column].unit if b.column in dataset.columns else b.unit)
                for v in data[b.column]
            ]
            for b in [bindings.measured[k] for k in targets]
        ]
    )
    scales = np.maximum(np.nanmedian(abs(measured), axis=0), 1e-12)
    runner = engine if engine is not None else Engine(on_error="raise")
    initial_values = {field: getattr(target, field) for field in fields}
    refs = {parameter.name: parameter for parameter in target.calibratable_parameters(False)}
    sizes, scale_x, initial, lower, upper = {}, [], [], [], []
    for field in fields:
        value = getattr(target, field)
        if value is None or isinstance(value, bool):
            raise ValueError(f"{module_path}.{field}: requires a numeric initial value")
        values = np.atleast_1d(np.asarray(value, dtype=float))
        sizes[field] = (len(values), isinstance(value, (list, tuple)))
        scale = np.maximum(np.abs(values), 1e-30)
        scale[values == 0] = 1
        scale_x.extend(scale)
        initial.extend(values / scale)
        bounds = refs[field].bounds
        low = bounds.get("ge", bounds.get("gt", -np.inf))
        high = bounds.get("le", bounds.get("lt", np.inf))
        if "gt" in bounds:
            low = np.nextafter(low, np.inf)
        if "lt" in bounds:
            high = np.nextafter(high, -np.inf)
        lower.extend(np.full(len(values), low) / scale)
        upper.extend(np.full(len(values), high) / scale)
    scale_x = np.asarray(scale_x)

    def unpack(x):
        values, offset = {}, 0
        for key, (size, vector) in sizes.items():
            part = (x[offset : offset + size] * scale_x[offset : offset + size]).tolist()
            values[key] = part if vector else part[0]
            offset += size
        return values

    valid = None

    def residual(x):
        nonlocal valid
        target.update_params(**unpack(x))
        predictions = runner.replay(trial, dataset, only=[module_path]).to_frame()
        if module_path not in predictions.columns.get_level_values(0):
            raise ValueError(f"{module_path}: no complete calibration observations")
        values = predictions[module_path].reindex(data.index)[targets].to_numpy(dtype=float)
        if valid is None:
            valid = np.isfinite(values).all(axis=1) & np.isfinite(measured).all(axis=1)
            if not valid.any():
                raise ValueError(f"{module_path}: no complete calibration observations")
        return ((values[valid] - measured[valid]) / scales).ravel()

    initial = np.asarray(initial)
    before_values = residual(initial).reshape(-1, len(targets))
    guess = initial.copy()
    if original.name == "heat_exchanger" and fields == ["ua"]:

        def raw_values(binding):
            unit = (
                dataset.columns[binding.column].unit
                if binding.column in dataset.columns
                else binding.unit
            )
            return np.array([to_si(value, unit) for value in data[binding.column]])

        hot_in = raw_values(bindings.inlets["hot_in"]["T"])
        cold_in = raw_values(bindings.inlets["cold_in"]["T"])
        hot_out = measured[:, targets.index("hot_out_T")]
        cold_out = measured[:, targets.index("cold_out_T")]
        duty = measured[:, targets.index("duty")]
        if original.arrangement == "counterflow":
            differences = zip(hot_in - cold_out, hot_out - cold_in)
        else:
            differences = zip(hot_in - cold_in, hot_out - cold_out)
        apparent = [
            q / delta
            for q, pair in zip(duty, differences)
            if (delta := heat_transfer.lmtd(max(0, pair[0]), max(0, pair[1]))) > 0
        ]
        if apparent:
            guess = np.asarray([np.median(apparent)]) / scale_x
    if original.name == "esp" and fields == ["head_coeff"] and "head" in targets:

        def raw(binding):
            unit = (
                dataset.columns[binding.column].unit
                if binding.column in dataset.columns
                else binding.unit
            )
            return np.array([to_si(v, unit) for v in data[binding.column]])

        flow_binding = bindings.inlets["suction"]["m_dot"]
        flows = raw(flow_binding)
        flow_unit = (
            dataset.columns[flow_binding.column].unit
            if flow_binding.column in dataset.columns
            else flow_binding.unit
        )
        if flow_unit == "kg/s":
            pressures = raw(bindings.inlets["suction"]["p"])
            temperatures = raw(bindings.inlets["suction"]["T"])
            flows /= np.array(
                [target.fluid.properties(p, t).density for p, t in zip(pressures, temperatures)]
            )
        coefficients = original.fit_head_coefficients(
            flows[valid],
            raw(bindings.controls["frequency"])[valid],
            measured[valid, targets.index("head")],
            target.no_stages,
        )
        guess = np.asarray(coefficients) / scale_x
    fitted = least_squares(
        residual,
        guess,
        bounds=(lower, upper),
        x_scale="jac",
        max_nfev=200,
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
    )
    values = unpack(fitted.x)
    after_values = residual(fitted.x).reshape(-1, len(targets))
    applied = bool(apply and fitted.success)
    if applied:
        original.update_params(**values)
    return CalibrationResult(
        values,
        float(np.sqrt(np.mean(before_values**2))),
        float(np.sqrt(np.mean(after_values**2))),
        int(valid.sum()),
        bool(fitted.success),
        fitted.message,
        applied,
        initial_values,
        dict(zip(targets, np.sqrt(np.mean(before_values**2, axis=0)).tolist())),
        dict(zip(targets, np.sqrt(np.mean(after_values**2, axis=0)).tolist())),
        fitted.nfev,
    )
