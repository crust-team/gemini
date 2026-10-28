"""Example doublet heat plant with every equipment connection written explicitly."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module
from gemini.core.types import HeatFlow, ModuleResult, PowerFlow, Stream
from gemini.core.types.quantities import Frequency, MassFlow, Power, Pressure, Ratio


class DoubletHeatPlant(Module):
    """Doublet, degasser, filters, heat exchanger and injection pump in diagram order."""

    name = "doublet_heat"
    category = "plant"
    description = "Handwritten doublet, surface heat extraction and reinjection plant."
    inlets = {}
    outlets = {
        "secondary_out": Stream,
        "gas": Stream,
        "electricity": PowerFlow,
        "heat_loss": HeatFlow,
    }

    class Inputs(BaseModel):
        """Imposed flow, drive controls and secondary-loop boundary conditions."""

        model_config = ConfigDict(extra="forbid")
        m_dot: MassFlow = Field(ge=0, description="Production rate [kg/s]")
        esp_frequency: Frequency = Field(description="ESP drive frequency [Hz]")
        injection_pressure: Pressure = Field(description="Injection pump discharge setpoint [Pa]")
        injection_frequency: Frequency = Field(60, description="Injection drive frequency [Hz]")
        secondary: Stream = Field(description="Secondary-loop inlet stream [-]")

    class Outputs(BaseModel):
        """Delivered heat and total predicted electrical consumption."""

        thermal_power: Power = Field(description="Secondary heat delivered [W]")
        electricity: Power = Field(description="Predicted total grid consumption [W]")
        cop: Ratio | None = Field(description="Heat/electricity; absent at zero consumption [-]")

    def __init__(
        self,
        doublet=None,
        degasser=None,
        filter_hot=None,
        heat_exchanger=None,
        filter_return=None,
        injection_pump=None,
    ):
        """Register supplied children; an empty instance can be filled by the legacy bridge."""
        super().__init__()
        for name, module in (
            ("doublet", doublet),
            ("degasser", degasser),
            ("filter_hot", filter_hot),
            ("heat_exchanger", heat_exchanger),
            ("filter_return", filter_return),
            ("injection_pump", injection_pump),
        ):
            if module is not None:
                setattr(self, name, module)

    def forward(self, inputs, streams_in):
        """Connect the two doublet limbs through the explicitly modeled surface equipment."""
        supply, esp_power, production_heat = self.doublet.produce(
            {"m_dot": inputs.m_dot, "esp_frequency": inputs.esp_frequency}
        )
        degassed = self.degasser(inlet=supply)
        filtered = self.filter_hot(inlet=degassed.streams["liquid"])
        exchanged = self.heat_exchanger(hot_in=filtered.streams["outlet"], cold_in=inputs.secondary)
        returned = self.filter_return(inlet=exchanged.streams["hot_out"])
        pumped = self.injection_pump(
            {
                "discharge_pressure": inputs.injection_pressure,
                "frequency": inputs.injection_frequency,
            },
            suction=returned.streams["outlet"],
        )
        injection_heat = self.doublet.inject(pumped.streams["discharge"])
        electricity = esp_power.P + pumped.streams["electricity"].P
        heat = exchanged.outputs.duty
        return ModuleResult(
            self.Outputs(
                thermal_power=heat,
                electricity=electricity,
                cop=heat / electricity if electricity else None,
            ),
            {
                "secondary_out": exchanged.streams["cold_out"],
                "gas": degassed.streams["gas"],
                "electricity": PowerFlow(P=electricity),
                "heat_loss": HeatFlow(Q=production_heat.Q + injection_heat.Q),
            },
        )
