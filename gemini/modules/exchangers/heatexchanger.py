"""Two-stream effectiveness-NTU heat exchanger."""

from typing import Literal

import numpy as np

from gemini import ops
from gemini.errors import InsufficientDataError, PhysicsRangeError, UnknownCorrelationError
from gemini.modules.module import Module
from gemini.physics import heat_transfer, hydraulics
from gemini.types import (
    Duty,
    Fraction,
    Health,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    PressureDifference,
    Ratio,
    Stream,
    Temperature,
    TemperatureDifference,
    ThermalConductance,
)
from gemini.types.results import NOT_ASSESSED


class HeatExchanger(Module):
    """Two-stream heat exchanger with thermal and fouling diagnostics."""

    repr_fields = ("ua", "arrangement", "dp_hot_nominal", "dp_cold_nominal")

    def __init__(self):
        """Declare exchanger design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.ua = Parameter(ThermalConductance, calibratable=True)
        self.arrangement = Parameter(Literal["counterflow", "parallel"], default="counterflow")
        self.dp_hot_nominal = Parameter(PressureDifference, ge=0)
        self.dp_cold_nominal = Parameter(PressureDifference, ge=0)
        self.m_dot_hot_nominal = Parameter(MassFlow, gt=0)
        self.m_dot_cold_nominal = Parameter(MassFlow, gt=0)
        self.fouling_threshold = Parameter(Fraction, default=0.15, gt=0, le=1)

        # Inlets
        self.hot_in = Inlet(Stream)
        self.cold_in = Inlet(Stream)

        # Outputs
        self.duty = Output(Duty, soft_sensor=True)
        self.effectiveness = Output(Fraction, soft_sensor=True)
        self.ntu = Output(Ratio)
        self.lmtd = Output(TemperatureDifference)
        self.hot_out_T = Output(Temperature)
        self.cold_out_T = Output(Temperature)
        self.dp_hot = Output(PressureDifference)
        self.dp_cold = Output(PressureDifference)
        self.approach_T = Output(TemperatureDifference)

        # Outlets
        self.hot_out = Outlet(Stream)
        self.cold_out = Outlet(Stream)

    def forward(self, inlets):
        """Solve the heat balance and retain both streams' mass flows."""

        # Outlets
        hot_in = inlets.hot_in
        cold_in = inlets.cold_in
        values = self._performance(hot_in, cold_in)

        hot_out = hot_in.with_(T=values["hot_out_T"], p=hot_in.p - values["dp_hot"])
        cold_out = cold_in.with_(T=values["cold_out_T"], p=cold_in.p - values["dp_cold"])

        outlets = dict(hot_out=hot_out, cold_out=cold_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        hot_in = inlets.hot_in
        cold_in = inlets.cold_in
        values = self._performance(hot_in, cold_in)
        for name, value in values.items():
            setattr(self, name, value)

    def _performance(self, hot_in, cold_in):
        ops.check(
            ops.logical_and(hot_in.m_dot >= 0, cold_in.m_dot >= 0),
            PhysicsRangeError,
            "{path}: negative mass flow hot_in.m_dot = {hot_m_dot} kg/s, "
            "cold_in.m_dot = {cold_m_dot} kg/s; expected >= 0",
            path=self.path,
            hot_m_dot=hot_in.m_dot,
            cold_m_dot=cold_in.m_dot,
        )
        ops.check(
            hot_in.T >= cold_in.T,
            PhysicsRangeError,
            "{path}: hot inlet is below cold inlet: hot_in.T = {hot_T} K, "
            "cold_in.T = {cold_T} K",
            path=self.path,
            hot_T=hot_in.T,
            cold_T=cold_in.T,
        )
        effectiveness, ntu, duty, hot_T, cold_T = self._heat_balance(hot_in, cold_in)
        dp_hot = hydraulics.quadratic_pressure_drop(
            self.dp_hot_nominal, hot_in.m_dot, self.m_dot_hot_nominal
        )
        dp_cold = hydraulics.quadratic_pressure_drop(
            self.dp_cold_nominal, cold_in.m_dot, self.m_dot_cold_nominal
        )
        if self.arrangement == "counterflow":
            dt1, dt2 = hot_in.T - cold_T, hot_T - cold_in.T
        else:
            dt1, dt2 = hot_in.T - cold_in.T, hot_T - cold_T
        return {
            "duty": duty,
            "effectiveness": effectiveness,
            "ntu": ntu,
            "lmtd": heat_transfer.lmtd(ops.maximum(0.0, dt1), ops.maximum(0.0, dt2)),
            "hot_out_T": hot_T,
            "cold_out_T": cold_T,
            "dp_hot": dp_hot,
            "dp_cold": dp_cold,
            "approach_T": ops.minimum(dt1, dt2),
        }

    def _heat_balance(self, hot_in, cold_in):
        """Return effectiveness, NTU, duty [W] and both outlet temperatures [K].

        A stopped stream (zero heat capacity rate) transfers no heat.
        """
        c_hot, c_cold = hot_in.heat_capacity_rate(), cold_in.heat_capacity_rate()
        c_min, c_max = ops.minimum(c_hot, c_cold), ops.maximum(c_hot, c_cold)
        stopped = c_min == 0
        ntu = heat_transfer.ntu(self.ua, c_min)
        method = (
            heat_transfer.effectiveness_counterflow
            if self.arrangement == "counterflow"
            else heat_transfer.effectiveness_parallel
        )
        effectiveness = method(ntu, c_min / c_max)
        duty = effectiveness * c_min * (hot_in.T - cold_in.T)
        hot_T = hot_in.T - duty / c_hot
        cold_T = cold_in.T + duty / c_cold
        return (
            ops.where(stopped, 0.0, effectiveness),
            ops.where(stopped, 0.0, ntu),
            ops.where(stopped, 0.0, duty),
            ops.where(stopped, hot_in.T, hot_T),
            ops.where(stopped, cold_in.T, cold_T),
        )

    @classmethod
    def ua_from_measurements(
        cls,
        hot_in_T,
        hot_out_T,
        cold_in_T,
        cold_out_T,
        m_dot_hot,
        m_dot_cold,
        *,
        cp_hot=heat_transfer.DEFAULT_CP,
        cp_cold=heat_transfer.DEFAULT_CP,
        arrangement="counterflow",
    ):
        """Estimate apparent UA [W/K] from measured temperatures and mass flows.

        Raises ``InsufficientDataError`` when the measurements cannot determine UA: a stopped
        stream, hot and cold duties that disagree by more than 5 %, or no positive LMTD.
        """
        name = cls.__name__
        if arrangement not in {"counterflow", "parallel"}:
            raise UnknownCorrelationError(
                f"{name}: unknown arrangement {arrangement!r}; expected counterflow or parallel"
            )
        apparent, code, qh, qc, delta = heat_transfer.apparent_conductance(
            arrangement,
            hot_in_T,
            hot_out_T,
            cold_in_T,
            cold_out_T,
            m_dot_hot,
            m_dot_cold,
            cp_hot,
            cp_cold,
        )
        if code == heat_transfer.NONPOSITIVE_INPUT:
            raise InsufficientDataError(f"{name}: mass flows and heat capacities must be positive")
        if code == heat_transfer.DISAGREEING_DUTIES:
            raise InsufficientDataError(
                f"{name}: hot/cold duties must agree within 5%; got {qh} W and {qc} W"
            )
        if code == heat_transfer.NO_LMTD:
            raise InsufficientDataError(f"{name}: positive LMTD required; got {delta} K")
        return apparent

    def health(self, result, measured):
        """Alarm when apparent conductance falls below the configured design fraction.

        With measured outlet temperatures, the inlet temperatures, mass flows and heat capacities
        come from the call's inlet streams. Returns ``None`` (not assessed) when a measurement is
        missing, the design UA is zero, or no row of the measurements can determine an apparent
        UA (see ``ua_from_measurements``). On arrays the rows that cannot are not ``assessed``,
        as a module without health reports them: score one, no alarm, ``NOT_ASSESSED``, NaN metrics.
        """
        if {"hot_out_T", "cold_out_T"} <= measured.keys():
            measured = measured | _inlet_measurements(result.inlets)
        keys = ("hot_in_T", "hot_out_T", "cold_in_T", "cold_out_T", "m_dot_hot", "m_dot_cold")
        if not set(keys) <= measured.keys() or not self.ua:
            return None
        apparent, code, _, _, _ = heat_transfer.apparent_conductance(
            self.arrangement,
            *(measured[key] for key in keys),
            measured.get("cp_hot", heat_transfer.DEFAULT_CP),
            measured.get("cp_cold", heat_transfer.DEFAULT_CP),
        )
        assessed = code == heat_transfer.DETERMINED
        if not np.any(assessed):
            return None
        ratio = apparent / self.ua
        alarm = ratio < 1 - self.fouling_threshold
        return Health(
            assessed=assessed,
            score=ops.where(assessed, ops.minimum(1, ops.maximum(0, ratio)), 1.0),
            alarm=ops.where(assessed, alarm, False),
            message=ops.where(
                assessed,
                ops.where(alarm, "Apparent UA below fouling limit", "Apparent UA within limit"),
                NOT_ASSESSED,
            ),
            metrics={
                "apparent_ua": ops.where(assessed, apparent, float("nan")),
                "ua_ratio": ops.where(assessed, ratio, float("nan")),
            },
        )


def _inlet_measurements(inlets):
    """Return inlet temperatures [K], mass flows [kg/s] and heat capacities [J/kg/K]."""
    hot, cold = inlets.hot_in, inlets.cold_in
    return dict(
        hot_in_T=hot.T,
        cold_in_T=cold.T,
        m_dot_hot=hot.m_dot,
        m_dot_cold=cold.m_dot,
        cp_hot=hot.fluid.properties(hot.p, hot.T).cp_l,
        cp_cold=cold.fluid.properties(cold.p, cold.T).cp_l,
    )
