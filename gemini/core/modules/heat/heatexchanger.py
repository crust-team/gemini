"""Plate heat exchanger between geothermal brine and the clean secondary loop.

Uses the standard effectiveness–NTU method for counterflow or parallel flow,
with first-law energy balance and quadratic hydraulic pressure losses.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.base.health import Health
from gemini.core.modules.module import Module, ModuleResult
from gemini.core.physics import fluid, heat_transfer


class HeatExchanger(Module):
    """Two-stream heat exchanger with thermal and fouling diagnostics."""

    name = "heatexchanger"
    category = "heat"
    description = "Plate heat exchanger with effectiveness–NTU performance and UA monitoring."
    inlets = ("hot_in", "cold_in")
    outlets = ("hot_out", "cold_out")
    soft_sensors = ("duty", "effectiveness")
    calibratable = ("ua",)

    class Params(BaseModel):
        """Thermal conductance and nominal hydraulic operating point."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        ua: float = Field(..., ge=0, description="Overall heat conductance [W/K]")
        arrangement: Literal["counterflow", "parallel"] = Field(
            "counterflow", description="Flow arrangement [-]"
        )
        dp_hot_nominal: float = Field(..., ge=0, description="Hot-side nominal pressure loss [Pa]")
        dp_cold_nominal: float = Field(
            ..., ge=0, description="Cold-side nominal pressure loss [Pa]"
        )
        m_dot_hot_nominal: float = Field(..., gt=0, description="Hot-side nominal mass flow [kg/s]")
        m_dot_cold_nominal: float = Field(
            ..., gt=0, description="Cold-side nominal mass flow [kg/s]"
        )
        fouling_threshold: float = Field(
            0.15, gt=0, le=1, description="Fractional UA decline triggering alarm [-]"
        )

    class Inputs(BaseModel):
        """The inlet streams supply all operating conditions."""

        model_config = ConfigDict(extra="forbid")

    class Outputs(BaseModel):
        """Thermal transfer, outlet temperatures and pressure losses."""

        duty: float = Field(..., description="Transferred thermal power [W]")
        effectiveness: float = Field(
            ..., description="Fraction of maximum possible heat transfer [-]"
        )
        ntu: float = Field(..., description="Number of transfer units [-]")
        lmtd: float = Field(..., description="Logarithmic mean temperature difference [K]")
        hot_out_T: float = Field(..., description="Hot-side outlet temperature [K]")
        cold_out_T: float = Field(..., description="Cold-side outlet temperature [K]")
        dp_hot: float = Field(..., description="Hot-side pressure loss [Pa]")
        dp_cold: float = Field(..., description="Cold-side pressure loss [Pa]")
        approach_T: float = Field(..., description="Minimum terminal temperature approach [K]")

    def forward(self, inputs, streams_in):
        """Solve the heat balance and retain both streams' mass flows."""
        hot, cold = streams_in["hot_in"], streams_in["cold_in"]
        if hot.m_dot < 0 or cold.m_dot < 0:
            raise ValueError(f"heatexchanger: negative mass flows {hot.m_dot}, {cold.m_dot}")
        if hot.T < cold.T:
            raise ValueError(f"heatexchanger: hot inlet {hot.T} K is below cold inlet {cold.T} K")
        cp_h = fluid.get_fluid(hot.fluid).properties(hot.p, hot.T).cp_l
        cp_c = fluid.get_fluid(cold.fluid).properties(cold.p, cold.T).cp_l
        c_hot, c_cold = hot.m_dot * cp_h, cold.m_dot * cp_c
        c_min, c_max = min(c_hot, c_cold), max(c_hot, c_cold)
        if c_min == 0:
            effectiveness = transfer_units = duty = 0.0
            Th, Tc = hot.T, cold.T
        else:
            transfer_units = heat_transfer.ntu(self.params.ua, c_min)
            method = (
                heat_transfer.effectiveness_counterflow
                if self.params.arrangement == "counterflow"
                else heat_transfer.effectiveness_parallel
            )
            effectiveness = method(transfer_units, c_min / c_max)
            duty = effectiveness * c_min * (hot.T - cold.T)
            Th, Tc = hot.T - duty / c_hot, cold.T + duty / c_cold
        dp_h = self.params.dp_hot_nominal * (hot.m_dot / self.params.m_dot_hot_nominal) ** 2
        dp_c = self.params.dp_cold_nominal * (cold.m_dot / self.params.m_dot_cold_nominal) ** 2
        if self.params.arrangement == "counterflow":
            dt1, dt2 = hot.T - Tc, Th - cold.T
        else:
            dt1, dt2 = hot.T - cold.T, Th - Tc
        out = self.Outputs(
            duty=duty,
            effectiveness=effectiveness,
            ntu=transfer_units,
            lmtd=heat_transfer.lmtd(max(0, dt1), max(0, dt2)),
            hot_out_T=Th,
            cold_out_T=Tc,
            dp_hot=dp_h,
            dp_cold=dp_c,
            approach_T=min(dt1, dt2),
        )
        return ModuleResult(
            out,
            {
                "hot_out": hot.with_(T=Th, p=hot.p - dp_h),
                "cold_out": cold.with_(T=Tc, p=cold.p - dp_c),
            },
        )

    @classmethod
    def ua_from_measurements(
        cls,
        hot_in_T: float,
        hot_out_T: float,
        cold_in_T: float,
        cold_out_T: float,
        m_dot_hot: float,
        m_dot_cold: float,
        *,
        cp_hot: float = 4217.4,
        cp_cold: float = 4217.4,
        arrangement: str = "counterflow",
    ) -> float:
        """Estimate apparent UA [W/K] from measured temperatures and mass flows.

        Parameters
        ----------
        hot_in_T, hot_out_T, cold_in_T, cold_out_T : float
            Measured terminal temperatures [K].
        m_dot_hot, m_dot_cold : float
            Positive mass flows [kg/s].
        cp_hot, cp_cold : float
            Liquid heat capacities [J/kg/K].
        arrangement : str
            Counterflow or parallel flow [-].

        Returns
        -------
        float
            Mean of the two measured duties divided by LMTD [W/K]. Duties
            must agree within 5 percent; this is an apparent-UA energy balance.
        """
        if min(m_dot_hot, m_dot_cold, cp_hot, cp_cold) <= 0:
            raise ValueError(
                "heatexchanger: measured mass flows and heat capacities must be positive"
            )
        qh = m_dot_hot * cp_hot * (hot_in_T - hot_out_T)
        qc = m_dot_cold * cp_cold * (cold_out_T - cold_in_T)
        if min(qh, qc) <= 0 or abs(qh - qc) / max(qh, qc) > 0.05:
            raise ValueError(
                "heatexchanger: measured positive hot/cold duties must agree within 5%"
            )
        if arrangement == "counterflow":
            dt1, dt2 = hot_in_T - cold_out_T, hot_out_T - cold_in_T
        elif arrangement == "parallel":
            dt1, dt2 = hot_in_T - cold_in_T, hot_out_T - cold_out_T
        else:
            raise ValueError(f"heatexchanger: unknown arrangement {arrangement!r}")
        delta = heat_transfer.lmtd(dt1, dt2)
        if delta <= 0:
            raise ValueError("heatexchanger: positive LMTD required to infer finite UA")
        return (qh + qc) / 2 / delta

    def health(self, predicted, measured):
        """Alarm when apparent conductance falls below the configured fraction of design UA."""
        keys = ("hot_in_T", "hot_out_T", "cold_in_T", "cold_out_T", "m_dot_hot", "m_dot_cold")
        if not set(keys) <= measured.keys():
            return None
        ua = self.ua_from_measurements(
            **{key: measured[key] for key in keys}, arrangement=self.params.arrangement
        )
        ratio = ua / self.params.ua if self.params.ua else 1.0
        return Health(
            score=min(1, max(0, ratio)),
            alarm=ratio < 1 - self.params.fouling_threshold,
            message=(
                "Apparent UA below fouling limit"
                if ratio < 1 - self.params.fouling_threshold
                else "Apparent UA within limit"
            ),
            metrics={"apparent_ua": ua, "ua_ratio": ratio},
        )
