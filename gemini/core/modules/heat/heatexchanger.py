"""Two-stream effectiveness-NTU heat exchanger."""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.physics import heat_transfer
from gemini.core.types import (
    Fraction,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Power,
    PressureDifference,
    Ratio,
    Stream,
    Temperature,
    TemperatureDifference,
    ThermalConductance,
)
from gemini.core.types.results import Health


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
        self.duty = Output(Power, soft_sensor=True)
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

    def forward(self, hot_in, cold_in):
        """Solve the heat balance and retain both streams' mass flows."""
        if hot_in.m_dot < 0 or cold_in.m_dot < 0:
            raise ValueError(f"{self.path}: negative mass flow")
        if hot_in.T < cold_in.T:
            raise ValueError(f"{self.path}: hot inlet is below cold inlet")
        cp_h = hot_in.fluid.properties(hot_in.p, hot_in.T).cp_l
        cp_c = cold_in.fluid.properties(cold_in.p, cold_in.T).cp_l
        c_hot, c_cold = hot_in.m_dot * cp_h, cold_in.m_dot * cp_c
        c_min, c_max = min(c_hot, c_cold), max(c_hot, c_cold)
        if c_min == 0:
            self.effectiveness = self.ntu = self.duty = 0.0
            hot_T, cold_T = hot_in.T, cold_in.T
        else:
            self.ntu = heat_transfer.ntu(self.ua, c_min)
            method = (
                heat_transfer.effectiveness_counterflow
                if self.arrangement == "counterflow"
                else heat_transfer.effectiveness_parallel
            )
            self.effectiveness = method(self.ntu, c_min / c_max)
            self.duty = self.effectiveness * c_min * (hot_in.T - cold_in.T)
            hot_T = hot_in.T - self.duty / c_hot
            cold_T = cold_in.T + self.duty / c_cold
        self.dp_hot = self.dp_hot_nominal * (hot_in.m_dot / self.m_dot_hot_nominal) ** 2
        self.dp_cold = self.dp_cold_nominal * (cold_in.m_dot / self.m_dot_cold_nominal) ** 2
        if self.arrangement == "counterflow":
            dt1, dt2 = hot_in.T - cold_T, hot_T - cold_in.T
        else:
            dt1, dt2 = hot_in.T - cold_in.T, hot_T - cold_T
        self.lmtd = heat_transfer.lmtd(max(0, dt1), max(0, dt2))
        self.hot_out_T = hot_T
        self.cold_out_T = cold_T
        self.approach_T = min(dt1, dt2)
        return {
            "hot_out": hot_in.with_(T=hot_T, p=hot_in.p - self.dp_hot),
            "cold_out": cold_in.with_(T=cold_T, p=cold_in.p - self.dp_cold),
        }

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
        cp_hot=4217.4,
        cp_cold=4217.4,
        arrangement="counterflow",
    ):
        """Estimate apparent UA [W/K] from measured temperatures and mass flows."""
        if min(m_dot_hot, m_dot_cold, cp_hot, cp_cold) <= 0:
            raise ValueError("heat_exchanger: mass flows and heat capacities must be positive")
        qh = m_dot_hot * cp_hot * (hot_in_T - hot_out_T)
        qc = m_dot_cold * cp_cold * (cold_out_T - cold_in_T)
        if min(qh, qc) <= 0 or abs(qh - qc) / max(qh, qc) > 0.05:
            raise ValueError("heat_exchanger: hot/cold duties must agree within 5%")
        if arrangement == "counterflow":
            dt1, dt2 = hot_in_T - cold_out_T, hot_out_T - cold_in_T
        elif arrangement == "parallel":
            dt1, dt2 = hot_in_T - cold_in_T, hot_out_T - cold_out_T
        else:
            raise ValueError(f"heat_exchanger: unknown arrangement {arrangement!r}")
        delta = heat_transfer.lmtd(dt1, dt2)
        if delta <= 0:
            raise ValueError("heat_exchanger: positive LMTD required")
        return (qh + qc) / 2 / delta

    def health(self, predicted, measured):
        """Alarm when apparent conductance falls below the configured design fraction."""
        keys = ("hot_in_T", "hot_out_T", "cold_in_T", "cold_out_T", "m_dot_hot", "m_dot_cold")
        if not set(keys) <= measured.keys():
            return None
        apparent = self.ua_from_measurements(
            **{key: measured[key] for key in keys},
            cp_hot=measured.get("cp_hot", 4217.4),
            cp_cold=measured.get("cp_cold", 4217.4),
            arrangement=self.arrangement,
        )
        ratio = apparent / self.ua if self.ua else 1.0
        return Health(
            score=min(1, max(0, ratio)),
            alarm=ratio < 1 - self.fouling_threshold,
            message=(
                "Apparent UA below fouling limit"
                if ratio < 1 - self.fouling_threshold
                else "Apparent UA within limit"
            ),
            metrics={"apparent_ua": apparent, "ua_ratio": ratio},
        )
