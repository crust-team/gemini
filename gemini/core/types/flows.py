"""Immutable fluid streams exchanged by equipment ports."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.physics import units
from gemini.core.types.fluid import BRINE, Fluid
from gemini.core.types.quantities import MassFlow, Pressure, Temperature
from gemini.errors import CallError, UnitError


class Stream(BaseModel):
    """Fluid stream passed between component ports (SI units)."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    m_dot: MassFlow = Field(..., description="Mass flow; negative means reverse [kg/s]")
    T: Temperature = Field(..., description="Temperature [K]")
    p: Pressure = Field(..., description="Absolute pressure [Pa]")
    fluid: Fluid = Field(BRINE, description="Immutable composition and property model [-]")

    def __init__(self, **data):
        """Accept convenient public units while retaining SI model fields.

        ``flow`` accepts mass flow, or volume flow converted with the stream's fluid density;
        plain numbers are kg/s. ``fluid`` defaults to the runtime default fluid here, while
        ``model_validate`` bypasses this constructor and uses the ``BRINE`` field default.
        ``gemini.core.runtime`` is imported here because it imports ``core.types.fluid``;
        a module-level import would form an import cycle through ``gemini.core.types``.
        """
        from gemini.core import runtime

        fluid = runtime.get_default_fluid() if data.get("fluid") is None else data.get("fluid")
        fluid = Fluid.model_validate(fluid)
        temperature = units.value_in_si(data.get("T"), "K", "Stream.T")
        pressure = units.value_in_si(data.get("p"), "Pa", "Stream.p")
        if "flow" in data:
            if "m_dot" in data:
                raise CallError("Stream: pass either flow or m_dot, not both")
            data["m_dot"] = _mass_flow(data.pop("flow"), fluid, pressure, temperature)
        elif "m_dot" in data:
            data["m_dot"] = units.value_in_si(data["m_dot"], "kg/s", "Stream.m_dot")
        data.update(T=temperature, p=pressure, fluid=fluid)
        super().__init__(**data)

    def volumetric_flow(self) -> float:
        """Return signed mixture volume flow [m3/s] using the stream fluid."""
        return self.m_dot / self.fluid.properties(self.p, self.T).density

    def with_(self, **changes) -> "Stream":
        """Return a validated copy with updated SI stream fields.

        ``model_copy`` alone would bypass validation, including the physical pressure and
        temperature limits.
        """
        return type(self).model_validate(self.model_dump() | changes)


def _mass_flow(flow, fluid, pressure, temperature):
    """Return a public ``flow`` value as mass flow [kg/s], using density for volume units."""
    number, unit = units.split_quantity(flow)
    if isinstance(number, str):
        raise UnitError(
            f"Stream.flow: value = {flow!r}; expected a number [kg/s] or '<number> <unit>'"
        )
    if units.si_unit(unit) == "m3/s":
        volume = units.value_in_si(flow, "m3/s", "Stream.flow")
        return volume * fluid.properties(pressure, temperature).density
    return units.value_in_si(flow, "kg/s", "Stream.flow")
