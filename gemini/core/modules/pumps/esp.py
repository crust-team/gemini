"""Electrical submersible pump using the retained TNO polynomial basis."""

import numpy as np

from gemini.core import runtime
from gemini.core.modules.module import Module
from gemini.core.physics import constants, pumps, units
from gemini.core.types import (
    Control,
    Count,
    Dimensionless,
    Efficiency,
    Fraction,
    Frequency,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Power,
    Pressure,
    PressureDifference,
    Ratio,
    Stream,
    VolumeFlow,
)
from gemini.core.types.results import Health


class ESP(Module):
    """Electrical submersible pump installed inside a production well."""

    repr_fields = ("no_stages", "setting_depth", "motor_efficiency", "bep_flow")

    def __init__(self):
        """Declare ESP design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.no_stages = Parameter(Count)
        self.head_coeff = Parameter(list[float], shape=(6,), calibratable=True)
        self.power_coeff = Parameter(list[float], shape=(6,), calibratable=True)
        self.pump_type = Parameter(str | None, default=None)
        self.setting_depth = Parameter(Length, default=0)
        self.motor_efficiency = Parameter(Efficiency, default=1)
        self.min_flow = Parameter(VolumeFlow, default=0, ge=0)
        self.max_flow = Parameter(VolumeFlow, default=1, gt=0)
        self.bep_flow = Parameter(VolumeFlow, default=0.04, gt=0)
        self.correction_factor = Parameter(tuple[Dimensionless, PressureDifference], default=(1, 0))
        self.tubing = Parameter(Length | None, default=None, gt=0)
        self.drift_threshold = Parameter(Fraction, default=0.10, gt=0, le=1)

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.head = Output(PressureDifference, soft_sensor=True)
        self.power = Output(Power, soft_sensor=True)
        self.efficiency = Output(Dimensionless, soft_sensor=True)
        self.discharge_pressure = Output(Pressure, soft_sensor=True)
        self.flow = Output(VolumeFlow)
        self.in_operating_window = Output(bool)
        self.bep_ratio = Output(Ratio)
        self.electricity = Output(Power)

        # Outlets
        self.discharge = Outlet(Stream)

    def head_function(self, flow: float, frequency: float) -> float:
        """Return pump head [Pa] for flow [m3/s] and frequency [Hz]."""
        return pumps.head(flow, frequency, self.no_stages, self._coefficients(self.head_coeff))

    def power_function(self, flow: float, frequency: float) -> float:
        """Return shaft power [W] for flow [m3/s] and frequency [Hz]."""
        return pumps.power(flow, frequency, self.no_stages, self._coefficients(self.power_coeff))

    @staticmethod
    def efficiency_function(flow: float, head: float, power: float) -> float:
        """Return retained hydraulic efficiency as a fraction."""
        if power < 0.1:
            return 0.0
        return (
            units.m3s_to_bbl_per_day(flow)
            / constants.ESP_EFFICIENCY_FLOW_FACTOR
            * (head / power)
            * (units.bhp_to_w(1) / units.ft_head_to_pa(1))
        )

    def forward(self, suction):
        """Compute head and power and raise the suction-stream pressure."""

        flow = suction.volumetric_flow()
        if flow < 0:
            raise ValueError(f"{self.path}: reverse volume flow {flow} is unsupported")
        head = self.head_function(flow, self.frequency)

        # Outlets
        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, suction, discharge):
        self.flow = suction.volumetric_flow()
        self.head = self.head_function(self.flow, self.frequency)
        self.power = self.power_function(self.flow, self.frequency)
        self.efficiency = self.efficiency_function(self.flow, self.head, self.power)
        scale = self.frequency / constants.ESP_REFERENCE_FREQUENCY
        self.discharge_pressure = discharge.p
        self.in_operating_window = self.min_flow * scale <= self.flow <= self.max_flow * scale
        self.bep_ratio = self.flow / (self.bep_flow * scale)
        self.electricity = self.power / self.motor_efficiency

    @staticmethod
    def _coefficients(values):
        # NOTE(refactor): old monitoring uses NumPy float32 arithmetic when selected globally.
        return (
            np.asarray(values, dtype=np.float32) if runtime.get_precision() == "float32" else values
        )

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
            alarm=drift > self.drift_threshold or not predicted.in_operating_window,
            message=message,
            metrics=drifts,
        )

    @classmethod
    def fit_head_coefficients(cls, flows, frequencies, heads, no_stages: int) -> list[float]:
        """Fit six ascending US-basis head coefficients from SI observations."""
        q, f, h = map(lambda value: np.asarray(value, dtype=float), (flows, frequencies, heads))
        if q.shape != f.shape or q.shape != h.shape or q.ndim != 1 or len(q) < 6:
            raise ValueError("esp: at least six matching observations required")
        if no_stages <= 0 or np.any(f <= 0) or np.any(q < 0) or not np.isfinite([q, f, h]).all():
            raise ValueError("esp: fitting requires finite positive stages and frequencies")
        x = units.m3s_to_bbl_per_day(q)
        y = units.pa_to_ft_head(h) / (no_stages * (f / constants.ESP_REFERENCE_FREQUENCY) ** 2)
        if len(np.unique(x)) < 6:
            raise ValueError("esp: six distinct flow values are required")
        return np.polynomial.Polynomial.fit(x, y, 5).convert().coef.tolist()

    @classmethod
    def fit_head_correction(cls, measured, theoretical) -> tuple[float, float]:
        """Fit the retained affine VLP correction in Pa."""
        x, y = map(lambda value: np.asarray(value, dtype=float), (measured, theoretical))
        if x.shape != y.shape or len(x) < 2 or not np.isfinite([x, y]).all() or np.var(x) == 0:
            raise ValueError("esp: two or more finite, distinct measurements required")
        slope = np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2)
        return float(slope), float(y.mean() - slope * x.mean())

    def head_curve(self, frequency: float, n_points: int = 50) -> list[tuple[float, float]]:
        """Return plotting points as (flow [m3/s], head [Pa])."""
        if frequency <= 0 or n_points < 2:
            raise ValueError("esp: positive frequency and at least two curve points required")
        scale = frequency / constants.ESP_REFERENCE_FREQUENCY
        return [
            (float(flow), self.head_function(flow / scale, frequency))
            for flow in np.linspace(0, 2 * self.max_flow * scale, n_points)
        ]
