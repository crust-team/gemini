"""Boiler module supplying auxiliary heat to the geothermal loop.

Gas and electric boilers share a steady first-law heat balance with a capacity cap.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module
from gemini.core.types.results import ModuleResult


class Boiler(Module):
    """Auxiliary gas or electric boiler with a thermal capacity limit."""

    name = "boiler"
    category = "heat"
    description = "Auxiliary heat source with efficiency and capacity limits."
    inlets = ("inlet",)
    outlets = ("outlet",)

    class Params(BaseModel):
        """Nominal boiler design data."""

        model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
        fuel: Literal["gas", "electric"] = Field(..., description="Energy source [-]")
        capacity: float = Field(..., gt=0, description="Maximum thermal duty [W]")
        efficiency: float = Field(..., gt=0, le=1, description="Thermal efficiency [-]")

    class Inputs(BaseModel):
        """Outlet temperature target."""

        model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
        setpoint_T: float = Field(..., gt=0, description="Outlet temperature setpoint [K]")

    class Outputs(BaseModel):
        """Delivered heat and energy input."""

        duty: float = Field(..., description="Delivered thermal power [W]")
        fuel_or_power: float = Field(..., description="Fuel energy or electric power [W]")
        outlet_T: float = Field(..., description="Outlet temperature [K]")
        capped: bool = Field(..., description="Requested heat exceeds capacity [-]")

    def forward(self, inputs, streams_in):
        """Heat a forward stream up to its setpoint, conserving energy."""
        stream = streams_in["inlet"]
        if stream.m_dot < 0:
            raise ValueError(f"boiler: negative mass flow {stream.m_dot}")
        cp = self.fluid.properties(stream.p, stream.T).cp_l
        requested = stream.m_dot * cp * max(0, inputs.setpoint_T - stream.T)
        duty = min(requested, self.params.capacity)
        T = stream.T + duty / (stream.m_dot * cp) if stream.m_dot else stream.T
        return ModuleResult(
            self.Outputs(
                duty=duty,
                fuel_or_power=duty / self.params.efficiency,
                outlet_T=T,
                capped=requested > self.params.capacity,
            ),
            {"outlet": stream.with_(T=T)},
        )
