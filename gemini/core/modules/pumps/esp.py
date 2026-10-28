"""Electrical submersible pump module.

Predicts stage head, shaft power and efficiency using the original polynomial
basis. Reference: TNO 2022 R11363, Model-based monitoring of geothermal assets.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gemini.core.modules.module import Module
from gemini.core.physics import constants, pumps, units
from gemini.core.types.quantities import (
    Count,
    Dimensionless,
    Fraction,
    Frequency,
    Length,
    Power,
    Pressure,
    PressureDifference,
    Ratio,
    VolumeFlow,
)
from gemini.core.types.results import Health, ModuleResult


class ESP(Module):
    """Electrical submersible pump installed inside a production well."""

    name = "esp"
    category = "pumps"
    description = "Submersible pump head, power, efficiency and operating-window monitoring."
    inlets = ("suction",)
    outlets = ("discharge",)
    soft_sensors = ("head", "power", "efficiency", "discharge_pressure")
    calibratable = ("head_coeff", "power_coeff")

    class Params(BaseModel):
        """Design data with legacy US-basis polynomial coefficients."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        coefficient_precision: Literal["float64", "float32"] = Field(
            "float64", description="Polynomial arithmetic precision for legacy runtime parity [-]"
        )
        no_stages: Count = Field(..., gt=0, description="Number of pump stages [-]")
        head_coeff: list[float] = Field(
            ...,
            min_length=6,
            max_length=6,
            description="Ascending polynomial coefficients, ft/stage versus bbl/day [US basis]",
        )
        power_coeff: list[float] = Field(
            ...,
            min_length=6,
            max_length=6,
            description="Ascending polynomial coefficients, bhp/stage versus bbl/day [US basis]",
        )
        pump_type: str | None = Field(None, description="Pump model identifier [-]")
        setting_depth: Length = Field(0, ge=0, description="Measured installation depth [m]")
        min_flow: VolumeFlow = Field(
            0, ge=0, description="Minimum flow at reference frequency [m3/s]"
        )
        max_flow: VolumeFlow = Field(
            1, gt=0, description="Maximum flow at reference frequency [m3/s]"
        )
        bep_flow: VolumeFlow = Field(
            0.04, gt=0, description="Best-efficiency flow at reference frequency [m3/s]"
        )
        correction_factor: tuple[Dimensionless, PressureDifference] = Field(
            (1, 0), description="VLP discharge correction (slope [-], offset [Pa])"
        )
        tubing: Length | None = Field(None, gt=0, description="Tubing internal diameter [m]")
        drift_threshold: Fraction = Field(
            0.10, gt=0, le=1, description="Relative drift alarm threshold [-]"
        )

        @model_validator(mode="after")
        def operating_window(self):
            """Require an ordered operating window."""
            if self.max_flow < self.min_flow:
                raise ValueError("esp: max_flow must be >= min_flow")
            return self

    class Inputs(BaseModel):
        """Per-step electrical drive frequency."""

        model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
        frequency: Frequency = Field(..., gt=0, description="Drive frequency [Hz]")

    class Outputs(BaseModel):
        """Pump performance and monitoring metrics in SI units."""

        head: PressureDifference = Field(..., description="Pump pressure rise [Pa]")
        power: Power = Field(..., description="Pump shaft power [W]")
        efficiency: Dimensionless = Field(..., description="Hydraulic efficiency as a fraction [-]")
        discharge_pressure: Pressure = Field(..., description="Discharge pressure [Pa]")
        flow: VolumeFlow = Field(..., description="Pump volume flow [m3/s]")
        in_operating_window: bool = Field(
            ..., description="Flow within frequency-scaled bounds [-]"
        )
        bep_ratio: Ratio = Field(..., description="Flow divided by frequency-scaled BEP flow [-]")

    def _coefficients(self, values):
        # NOTE(refactor): old monitoring modules evaluate NumPy float32 coefficients and arithmetic.
        return (
            np.asarray(values, dtype=np.float32)
            if self.params.coefficient_precision == "float32"
            else values
        )

    def head_function(self, flow: float, frequency: float) -> float:
        """Return TNO R11363 pump head [Pa] for flow [m3/s] and frequency [Hz]."""
        return pumps.head(
            flow, frequency, self.params.no_stages, self._coefficients(self.params.head_coeff)
        )

    def power_function(self, flow: float, frequency: float) -> float:
        """Return TNO R11363 shaft power [W] for flow [m3/s] and frequency [Hz]."""
        return pumps.power(
            flow, frequency, self.params.no_stages, self._coefficients(self.params.power_coeff)
        )

    def efficiency_function(self, flow: float, head: float, power: float) -> float:
        """Return the original efficiency as a fraction from flow [m3/s], head [Pa], power [W]."""
        if power < 0.1:
            return 0.0
        # NOTE(refactor): original efficiency was percent; this API divides by 100, without
        # clipping.
        return (
            units.m3s_to_bbl_per_day(flow)
            / constants.ESP_EFFICIENCY_FLOW_FACTOR
            * (head / power)
            * (units.bhp_to_w(1) / units.ft_head_to_pa(1))
        )

    def forward(self, inputs, streams_in):
        """Compute head and power and raise the suction-stream pressure."""
        suction = streams_in["suction"]
        flow = suction.volumetric_flow()
        if flow < 0:
            raise ValueError(f"esp: reverse volume flow {flow} is unsupported")
        head = self.head_function(flow, inputs.frequency)
        power = self.power_function(flow, inputs.frequency)
        scale = inputs.frequency / constants.ESP_REFERENCE_FREQUENCY
        discharge = suction.with_(p=suction.p + head)
        # NOTE(refactor): correction_factor belongs to inferred VLP discharge, not theoretical head.
        result = self.Outputs(
            head=head,
            power=power,
            efficiency=self.efficiency_function(flow, head, power),
            discharge_pressure=discharge.p,
            flow=flow,
            in_operating_window=self.params.min_flow * scale
            <= flow
            <= self.params.max_flow * scale,
            bep_ratio=flow / (self.params.bep_flow * scale),
        )
        return ModuleResult(result, {"discharge": discharge})

    def health(self, predicted, measured):
        """Score the worst available relative drift and the operating window."""
        drifts = {
            key: (measured[key] - getattr(predicted, key))
            / max(abs(getattr(predicted, key)), 1e-12)
            for key in ("power", "head", "discharge_pressure")
            if key in measured
        }
        worst = max(drifts, key=lambda key: abs(drifts[key])) if drifts else None
        drift = abs(drifts[worst]) if worst else 0
        message = f"Worst drift: {worst}" if worst else "No performance measurements"
        if not predicted.in_operating_window:
            message += "; outside operating window"
        return Health(
            score=max(0, 1 - drift),
            alarm=drift > self.params.drift_threshold or not predicted.in_operating_window,
            message=message,
            metrics=drifts,
        )

    @classmethod
    def fit_head_coefficients(cls, flows, frequencies, heads, no_stages: int) -> list[float]:
        """Fit ascending US-basis head coefficients from flows [m3/s], Hz and heads [Pa].

        Fits the compute model's polynomial with frequency-squared scaling. At least
        six distinct flow values are required to determine all six coefficients.
        """
        q, f, h = map(lambda v: np.asarray(v, dtype=float), (flows, frequencies, heads))
        if q.shape != f.shape or q.shape != h.shape or q.ndim != 1 or len(q) < 6:
            raise ValueError(
                "esp: at least six matching flow, frequency and head observations required"
            )
        if no_stages <= 0 or np.any(f <= 0) or np.any(q < 0) or not np.isfinite([q, f, h]).all():
            raise ValueError(
                "esp: fitting requires finite observations, positive stages and frequencies"
            )
        x = units.m3s_to_bbl_per_day(q)
        y = units.pa_to_ft_head(h) / (no_stages * (f / constants.ESP_REFERENCE_FREQUENCY) ** 2)
        if len(np.unique(x)) < 6:
            raise ValueError("esp: six distinct flow values are required")
        # NOTE(refactor): old calibration fitted affine VLP correction, not polynomial coefficients.
        # Preserve that algorithm separately; this method fits the requested six coefficients.
        return np.polynomial.Polynomial.fit(x, y, 5).convert().coef.tolist()

    @classmethod
    def fit_head_correction(cls, measured, theoretical) -> tuple[float, float]:
        """Port the old affine fit: theoretical [Pa] = a * measured [Pa] + b [Pa]."""
        x, y = map(lambda v: np.asarray(v, dtype=float), (measured, theoretical))
        if x.shape != y.shape or len(x) < 2 or not np.isfinite([x, y]).all() or np.var(x) == 0:
            raise ValueError("esp: two or more finite, distinct measurements required")
        slope = np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2)
        return float(slope), float(y.mean() - slope * x.mean())

    def head_curve(self, frequency: float, n_points: int = 50) -> list[tuple[float, float]]:
        """Return the legacy plotting curve as (flow [m3/s], head [Pa]) pairs at frequency [Hz]."""
        if frequency <= 0 or n_points < 2:
            raise ValueError("esp: positive frequency and at least two curve points required")
        scale = frequency / constants.ESP_REFERENCE_FREQUENCY
        # NOTE(refactor): old plotting normalises flow by f/60; old calculate_output does not.
        return [
            (float(q), self.head_function(q / scale, frequency))
            for q in np.linspace(0, 2 * self.params.max_flow * scale, n_points)
        ]
