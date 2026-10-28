"""Historical replay and bounded parameter calibration against measured outputs."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from gemini.core.engine.results import Results
from gemini.core.modes import twin


def replay(plant, config, data, start=None, end=None):
    """Replay each selected UTC observation on its independent measured equipment boundaries."""
    plant.config = config.model_copy(deep=True)
    data = data.copy()
    data.index = pd.to_datetime(data.index, utc=True)
    if start is not None:
        data = data.loc[
            (
                pd.Timestamp(start).tz_localize("UTC")
                if pd.Timestamp(start).tzinfo is None
                else start
            ) :
        ]
    if end is not None:
        data = data.loc[
            : pd.Timestamp(end).tz_localize("UTC") if pd.Timestamp(end).tzinfo is None else end
        ]
    plant.skip_counts = {}
    results = Results()
    for at, row in zip(data.index, data.to_dict("records")):
        results.append(at, twin.evaluate(plant, row, at))
    results.skip_counts = {key: dict(counts) for key, counts in plant.skip_counts.items()}
    return results


@dataclass(frozen=True)
class CalibrationResult:
    """Fitted design values and dimensionless residual RMS, without implicit application."""

    fitted: dict[str, Any]
    rms_before: float
    rms_after: float
    observations: int
    success: bool
    message: str
    applied: bool


def calibrate(
    plant, config, data, module_path, fields=None, method="least_squares", *, apply=False
):
    """Fit selected calibratable fields with bounded least squares and explicit application.

    Residuals are normalised per measured output by its median magnitude. The fit uses
    only the supplied window; no holdout measurements enter the objective.
    """
    if method != "least_squares":
        raise ValueError(f"Unknown calibration method {method!r}")
    original = plant.get_submodule(module_path)
    fields = list(original.calibratable if fields is None else fields)
    if not fields or set(fields) - set(original.calibratable):
        raise ValueError(f"{module_path}: fields must be nonempty and calibratable")
    bindings = config.bindings[module_path]
    defaults = config.boundary.get("stream_defaults", {}).get(module_path)
    samples = []
    snapshots = set()
    for at, row in zip(data.index, data.to_dict("records")):
        snapshots.add(config.modules[module_path].at(at).valid_from)
        try:
            samples.append(twin.prepare(original, bindings, row, defaults))
        except twin.MissingMeasurement:
            continue
    if not samples:
        raise ValueError(f"{module_path}: no complete calibration observations")
    if len(snapshots) != 1:
        raise ValueError("Calibrate one dated design snapshot at a time")
    baseline = config.modules[module_path].at(
        data.index[0]
    ).params | plant._parameter_overrides.get(module_path, {})
    trial = type(original)(baseline, fluid=original.fluid_name)
    targets = set(original.Outputs.model_fields) & set.intersection(*(set(s[2]) for s in samples))
    if original.name == "heatexchanger" and fields == ["ua"]:
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
    scales = {
        key: max(float(np.median([abs(s[2][key]) for s in samples])), 1e-12) for key in targets
    }
    refs = {ref.field: ref for ref in trial.calibratable_params(False)}
    sizes, scale_x, initial, lower, upper = {}, [], [], [], []
    for field in fields:
        value = getattr(trial.params, field)
        if value is None or isinstance(value, bool):
            raise ValueError(f"{module_path}.{field}: requires a numeric initial value")
        values = np.atleast_1d(np.asarray(value, dtype=float))
        sizes[field] = (len(values), isinstance(value, (list, tuple)))
        scale = np.maximum(np.abs(values), 1e-30)
        scale[values == 0] = 1
        scale_x.extend(scale)
        initial.extend(values / scale)
        low, high = refs[field].bounds or (-np.inf, np.inf)
        for constraint in trial.Params.model_fields[field].metadata:
            if getattr(constraint, "gt", None) is not None:
                low = np.nextafter(low, np.inf)
            if getattr(constraint, "lt", None) is not None:
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

    def residual(x):
        trial.update_params(**unpack(x))
        result = []
        for inputs, streams, measured in samples:
            prediction = trial(inputs, streams).outputs
            result.extend(
                (getattr(prediction, key) - measured[key]) / scales[key] for key in targets
            )
        return np.asarray(result)

    initial = np.asarray(initial)
    before = float(np.sqrt(np.mean(residual(initial) ** 2)))
    guess = initial.copy()
    if original.name == "esp" and fields == ["head_coeff"] and "head" in targets:
        coefficients = original.fit_head_coefficients(
            [s[1]["suction"].volumetric_flow() for s in samples],
            [s[0]["frequency"] for s in samples],
            [s[2]["head"] for s in samples],
            trial.params.no_stages,
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
    after = float(np.sqrt(np.mean(residual(fitted.x) ** 2)))
    applied = bool(apply and fitted.success)
    if applied:
        for field, value in values.items():
            plant.set_param(f"{module_path}.{field}", value)
        plant._parameter_overrides.setdefault(module_path, {}).update(values)
    return CalibrationResult(
        values, before, after, len(samples), bool(fitted.success), fitted.message, applied
    )
