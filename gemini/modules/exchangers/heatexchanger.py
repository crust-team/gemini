"""Two-stream effectiveness-NTU heat exchanger."""

from typing import Literal

import numpy as np

from gemini import ops
from gemini.errors import PhysicsRangeError
from gemini.modules.module import Module
from gemini.physics import diagnostics, heat_transfer, hydraulics
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
        self.fouling_threshold = Parameter(
            Fraction, default=diagnostics.DEFAULT_FOULING_THRESHOLD, gt=0, le=1
        )

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
        self._check_inlets(hot_in, cold_in)
        effectiveness, ntu, duty, hot_T, cold_T = heat_transfer.exchanger_balance(
            hot_in.T,
            cold_in.T,
            hot_in.heat_capacity_rate(),
            cold_in.heat_capacity_rate(),
            self.ua,
            self.arrangement == "counterflow",
        )
        dp_hot = hydraulics.quadratic_pressure_drop(
            self.dp_hot_nominal, hot_in.m_dot, self.m_dot_hot_nominal
        )
        dp_cold = hydraulics.quadratic_pressure_drop(
            self.dp_cold_nominal, cold_in.m_dot, self.m_dot_cold_nominal
        )
        dt1, dt2 = heat_transfer.terminal_differences(
            hot_in.T, hot_T, cold_in.T, cold_T, self.arrangement == "counterflow"
        )
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

    def _check_inlets(self, hot_in, cold_in):
        """Reject negative flow and a hot inlet below the cold inlet."""
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

    def health(self, result, measured):
        """Alarm when apparent conductance falls below the configured design fraction.

        With measured outlet temperatures, the inlet temperatures, mass flows and heat capacities
        come from the call's inlet streams. Returns ``None`` (not assessed) when a measurement is
        missing, the design UA is zero, or no row of the measurements can determine an apparent
        UA (see ``gm.analysis.estimate_conductance``). On arrays the rows that cannot are not
        ``assessed``, as a module without health reports them: score one, no alarm,
        ``NOT_ASSESSED``, NaN metrics.
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
        ratio = diagnostics.performance_ratio(apparent, self.ua)
        alarm = diagnostics.below_limit(ratio, self.fouling_threshold)
        return Health(
            assessed=assessed,
            score=ops.where(assessed, diagnostics.bounded_score(ratio), 1.0),
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
