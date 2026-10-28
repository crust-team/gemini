"""Immutable fluid streams exchanged by equipment ports."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.physics import units
from gemini.core.types.fluid import BRINE, Fluid
from gemini.core.types.quantities import MassFlow, Power, Pressure, Temperature


class Stream(BaseModel):
    """Fluid stream passed between component ports (SI units)."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    m_dot: MassFlow = Field(..., description="Mass flow; negative means reverse [kg/s]")
    T: Temperature = Field(..., gt=0, description="Temperature [K]")
    p: Pressure = Field(..., ge=0, description="Absolute pressure [Pa]")
    fluid: Fluid = Field(BRINE, description="Immutable composition and property model [-]")

    def __init__(self, **data):
        """Accept convenient public units while retaining SI model fields."""
        from gemini.core import runtime

        fluid = runtime.get_default_fluid() if data.get("fluid") is None else data.get("fluid")
        fluid = Fluid.model_validate(fluid)
        temperature = units.value_in_si(data.get("T"), "K", "Stream.T")
        pressure = units.value_in_si(data.get("p"), "Pa", "Stream.p")
        if "flow" in data:
            flow = data.pop("flow")
            supplied_unit = None
            if isinstance(flow, str):
                supplied_unit = flow.strip().split(maxsplit=1)[1]
            elif hasattr(flow, "unit"):
                supplied_unit = flow.unit
            if supplied_unit in {"m3/h", "m3/s", "l/s"}:
                volume = units.value_in_si(flow, "m3/s", "Stream.flow")
                flow = volume * fluid.properties(pressure, temperature).density
            else:
                flow = units.value_in_si(flow, "kg/s", "Stream.flow")
            data["m_dot"] = flow
        elif "m_dot" in data:
            data["m_dot"] = units.value_in_si(data["m_dot"], "kg/s", "Stream.m_dot")
        data.update(T=temperature, p=pressure, fluid=fluid)
        super().__init__(**data)

    def volumetric_flow(self) -> float:
        """Return signed mixture volume flow [m3/s] using the stream dtype."""
        return self.m_dot / self.fluid.properties(self.p, self.T).density

    def with_(self, **changes) -> "Stream":
        """Return a validated copy with updated SI stream fields."""
        # model_copy alone bypasses validation, including physical pressure/temperature limits.
        return type(self).model_validate(self.model_dump() | changes)


class PowerFlow(BaseModel):
    """Electrical power drawn by a module; positive means consumption [W]."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    P: Power


class FuelFlow(BaseModel):
    """Chemical energy consumed, measured on a lower-heating-value basis [W]."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    P: Power
    fuel: Literal["natural_gas", "hydrogen", "biogas"] = "natural_gas"


class HeatFlow(BaseModel):
    """Heat released to the environment, positive outward [W]."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    Q: Power
    T: Temperature | None = None


Flow = Stream | PowerFlow | FuelFlow | HeatFlow
