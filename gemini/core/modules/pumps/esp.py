"""Electrical submersible pump using the retained TNO polynomial basis."""

import numpy as np

from gemini import backends, ops
from gemini.core import runtime
from gemini.core.modules.module import Module
from gemini.core.physics import constants, pumps, units
from gemini.core.types import (
    Control,
    Count,
    Dimensionless,
    Efficiency,
    Electricity,
    Fraction,
    Frequency,
    Health,
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
from gemini.errors import ConfigurationError, InsufficientDataError, PhysicsRangeError
from gemini.ops import Constant

MIN_EFFICIENCY_POWER = Constant(
    "ESP_MIN_EFFICIENCY_POWER",
    0.1,
    "W",
    "shaft power below which the pump is treated as stopped and its efficiency as zero",
)

HYDRAULIC_POWER_PER_HEAD = units.bhp_to_w(1) / units.ft_head_to_pa(1)
"""Unit factor of the efficiency: [W per bhp] over [Pa per ft of head], computed once."""

HEALTH_KEYS = ("power", "head", "discharge_pressure")
"""Measured quantities whose relative drift from the prediction is scored."""

NO_MEASUREMENTS_OUTSIDE = "No performance measurements; outside operating window"

DRIFT_FLOOR = 1e-12
"""Smallest prediction magnitude used as a drift denominator, so a zero prediction is finite."""


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
        self.electricity = Output(Electricity)

        # Outlets
        self.discharge = Outlet(Stream)

    def _scalar_mode(self):
        """Return ``PLAIN`` under float32 precision, else ``WRAP``.

        NOTE(refactor): the legacy float32 arithmetic needs Python floats next to float32
        coefficients, and an ``np.float64`` scalar would promote them. This is the one module that
        honours float32 precision, so its ``efficiency_function`` keeps ``ops.truediv``: a
        plain ``/`` by a zero power would raise there.
        """
        return backends.PLAIN if runtime.get_precision() == "float32" else backends.WRAP

    def forward(self, inlets):
        """Raise the suction-stream pressure by the pump-curve head."""

        # Outlets
        suction = inlets.suction
        flow = suction.volumetric_flow()
        ops.check(
            flow >= 0,
            PhysicsRangeError,
            "{path}: suction volume flow = {flow} m3/s; reverse flow is unsupported",
            path=self.path,
            flow=flow,
        )
        head = self.head_function(flow, self.frequency)

        discharge = suction.with_(p=suction.p + head)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        suction = inlets.suction
        discharge = outlets.discharge
        self.flow = suction.volumetric_flow()
        self.head = self.head_function(self.flow, self.frequency)
        self.power = self.power_function(self.flow, self.frequency)
        self.efficiency = self.efficiency_function(self.flow, self.head, self.power)
        scale = self.frequency / constants.ESP_REFERENCE_FREQUENCY
        self.discharge_pressure = discharge.p
        self.in_operating_window = ops.logical_and(
            self.min_flow * scale <= self.flow, self.flow <= self.max_flow * scale
        )
        self.bep_ratio = self.flow / (self.bep_flow * scale)
        self.electricity = self.power / self.motor_efficiency

    def head_function(self, flow: float, frequency: float) -> float:
        """Return pump head [Pa] for flow [m3/s] and frequency [Hz]."""
        return pumps.head(flow, frequency, self.no_stages, self._coefficients(self.head_coeff))

    def power_function(self, flow: float, frequency: float) -> float:
        """Return shaft power [W] for flow [m3/s] and frequency [Hz]."""
        return pumps.power(flow, frequency, self.no_stages, self._coefficients(self.power_coeff))

    @staticmethod
    def efficiency_function(flow: float, head: float, power: float) -> float:
        """Return retained hydraulic efficiency as a fraction, zero for a stopped pump."""
        return ops.where(
            power < MIN_EFFICIENCY_POWER,
            0.0,
            units.m3s_to_bbl_per_day(flow)
            / constants.ESP_EFFICIENCY_FLOW_FACTOR
            * ops.truediv(head, power)
            * HYDRAULIC_POWER_PER_HEAD,
        )

    def health(self, result, measured):
        """Score the worst available relative drift and the operating window.

        Runs on scalars and on arrays over a chunk: the worst drift key and the message are
        selected with ``ops.where`` over complete strings, the first key winning a tie.
        """
        predicted = result.outputs
        window = predicted.in_operating_window
        drifts = {
            key: (measured[key] - getattr(predicted, key))
            / ops.maximum(ops.abs(getattr(predicted, key)), DRIFT_FLOOR)
            for key in HEALTH_KEYS
            if key in measured
        }
        worst, message = self._worst_drift(drifts, window)
        return Health(
            score=ops.maximum(0, 1 - worst),
            alarm=ops.logical_or(worst > self.drift_threshold, ops.logical_not(window)),
            message=message,
            metrics=drifts,
        )

    @staticmethod
    def _worst_drift(drifts, window):
        """Return the largest absolute drift and the message naming it and the window."""
        if not drifts:
            return 0, ops.where(window, "No performance measurements", NO_MEASUREMENTS_OUTSIDE)
        worst, message = None, None
        for key, drift in drifts.items():
            text = ops.where(
                window, f"Worst drift: {key}", f"Worst drift: {key}; outside operating window"
            )
            magnitude = ops.abs(drift)
            if worst is None:
                worst, message = magnitude, text
                continue
            larger = magnitude > worst
            worst, message = ops.where(larger, magnitude, worst), ops.where(larger, text, message)
        return worst, message

    @classmethod
    def fit_head_coefficients(cls, flows, frequencies, heads, no_stages: int) -> list[float]:
        """Fit six ascending US-basis head coefficients from SI observations."""
        q, f, h = map(lambda value: np.asarray(value, dtype=float), (flows, frequencies, heads))
        if q.shape != f.shape or q.shape != h.shape or q.ndim != 1 or len(q) < 6:
            raise InsufficientDataError(
                f"{cls.__name__}: at least six matching observations required"
            )
        if no_stages <= 0 or np.any(f <= 0) or np.any(q < 0) or not np.isfinite([q, f, h]).all():
            raise InsufficientDataError(
                f"{cls.__name__}: fitting requires finite positive stages and frequencies"
            )
        x = units.m3s_to_bbl_per_day(q)
        y = units.pa_to_ft_head(h) / (no_stages * (f / constants.ESP_REFERENCE_FREQUENCY) ** 2)
        if len(np.unique(x)) < 6:
            raise InsufficientDataError(f"{cls.__name__}: six distinct flow values are required")
        return np.polynomial.Polynomial.fit(x, y, 5).convert().coef.tolist()

    @classmethod
    def fit_head_correction(cls, measured, theoretical) -> tuple[float, float]:
        """Fit the retained affine VLP correction in Pa."""
        x, y = map(lambda value: np.asarray(value, dtype=float), (measured, theoretical))
        if x.shape != y.shape or len(x) < 2 or not np.isfinite([x, y]).all() or np.var(x) == 0:
            raise InsufficientDataError(
                f"{cls.__name__}: two or more finite, distinct measurements required"
            )
        slope = np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean()) ** 2)
        return float(slope), float(y.mean() - slope * x.mean())

    def head_curve(self, frequency: float, n_points: int = 50) -> list[tuple[float, float]]:
        """Return plotting points as (flow [m3/s], head [Pa])."""
        if frequency <= 0 or n_points < 2:
            raise ConfigurationError(
                f"{self.path}: positive frequency and at least two curve points required; got "
                f"frequency = {frequency} Hz, n_points = {n_points}"
            )
        scale = frequency / constants.ESP_REFERENCE_FREQUENCY
        return [
            (float(flow), self.head_function(flow / scale, frequency))
            for flow in np.linspace(0, 2 * self.max_flow * scale, n_points)
        ]

    @staticmethod
    def _coefficients(values):
        """Return curve coefficients in the selected runtime precision.

        NOTE(refactor): old monitoring uses NumPy float32 arithmetic when selected globally.
        """
        if runtime.get_precision() == "float32":
            return np.asarray(values, dtype=np.float32)
        return values
