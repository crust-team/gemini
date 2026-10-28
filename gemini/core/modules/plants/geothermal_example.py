"""The supplied GEMINI plant, with every equipment connection written explicitly."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module
from gemini.core.modules.plants.doublet import Doublet
from gemini.core.types import HeatFlow, ModuleResult, PowerFlow, Stream
from gemini.core.types.quantities import Frequency, MassFlow, Power, Pressure, Ratio


class GeothermalExamplePlant(Module):
    """Doublet, degasser, filters, heat exchanger and injection pump in diagram order."""

    name = "geothermal_example"
    category = "plant"
    description = "Handwritten configuration of the supplied geothermal doublet."
    inlets = {}
    outlets = {
        "secondary_out": Stream,
        "gas": Stream,
        "electricity": PowerFlow,
        "heat_loss": HeatFlow,
    }
    GEMINI_NODES = {
        "reservoir_c1b5": "doublet.reservoir",
        "production_well_c774": "doublet.well",
        "esp_1ee3": "doublet.esp",
        "degasser_e846": "degasser",
        "filter_b2e6": "filter_hot",
        "heat_exchanger_3410": "heat_exchanger",
        "filter_b1ed": "filter_return",
        "injection_pump_3808": "injection_pump",
        "injection_well_a06b": "doublet.injector",
        "reservoir_28fc": "doublet.sink",
    }
    # NOTE(refactor): the diagram omits the physical above-ESP riser. Verification
    # expands its ESP->surface edge into ESP->riser->surface, checking BOTH edges.
    DIAGRAM_EXPANSIONS = {("doublet.esp", "discharge"): ("doublet.riser", "bottom", "wellhead")}

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
        self, doublet, degasser, filter_hot, heat_exchanger, filter_return, injection_pump
    ):
        """Register the plant's children in a readable physical grouping."""
        super().__init__()
        self.doublet = doublet
        self.degasser = degasser
        self.filter_hot = filter_hot
        self.heat_exchanger = heat_exchanger
        self.filter_return = filter_return
        self.injection_pump = injection_pump

    @classmethod
    def from_config(cls, config, at=None):
        """Construct known children from dated design data; topology is defined in forward."""
        from gemini.core.modules.catalogue import create

        expected = set(cls.GEMINI_NODES.values()) | {"doublet.riser"}
        if set(config.modules) != expected:
            raise ValueError(f"Example plant child paths differ: {set(config.modules) ^ expected}")
        children = {
            name: create(item.type, item.at(at).params, fluid=item.fluid)
            for name, item in config.modules.items()
        }
        doublet = Doublet(
            **{
                name.removeprefix("doublet."): child
                for name, child in children.items()
                if name.startswith("doublet.")
            }
        )
        return cls(
            doublet=doublet,
            **{name: child for name, child in children.items() if not name.startswith("doublet.")},
        )

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
