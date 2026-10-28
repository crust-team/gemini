"""Define and run a custom plant with a doublet, heat exchanger and auxiliary boiler."""

from pathlib import Path

from pydantic import Field

from gemini.core.config.build import build_plant
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.modules.balance import collect_flows
from gemini.core.modules.heat.boiler import Boiler
from gemini.core.modules.module import Module
from gemini.core.modules.plants.doublet import Doublet
from gemini.core.types import WATER, ModuleResult, Stream
from gemini.core.types.quantities import Temperature


class HeatingPlant(Module):
    """A user-defined plant: child assignment registers it, forward defines its wiring."""

    name, category = "custom_heating", "plant"
    outlets = {"supply": Stream}

    class Inputs(Doublet.Inputs):
        """Production controls, secondary inlet and heating target."""

        secondary: Stream = Field(description="Heating return [-]")
        target: Temperature = Field(description="Heating supply temperature [K]")

    def __init__(self, doublet, exchanger):
        """Compose reusable equipment with a local auxiliary heat source."""
        super().__init__()
        self.doublet, self.exchanger = doublet, exchanger
        self.boiler = Boiler(dict(fuel="electric", capacity=1e6, efficiency=0.98))

    def forward(self, inputs, streams_in):
        """Connect geothermal production, heat transfer, reinjection and auxiliary heating."""
        hot, _, _ = self.doublet.produce(
            dict(m_dot=inputs.m_dot, esp_frequency=inputs.esp_frequency)
        )
        hx = self.exchanger(hot_in=hot, cold_in=inputs.secondary)
        self.doublet.inject(hx.streams["hot_out"])
        heated = self.boiler(dict(setpoint_T=inputs.target), inlet=hx.streams["cold_out"])
        return ModuleResult(self.Outputs(), {"supply": heated.streams["outlet"]})


base = build_plant(load_gemini(Path(__file__).parents[1] / "datasets/geothermal_doublet"))
plant = HeatingPlant(base.doublet, base.heat_exchanger)
result = plant(
    dict(
        m_dot=40,
        esp_frequency=60,
        target=340,
        secondary=Stream(m_dot=40, T=300, p=5e5, fluid=WATER),
    )
)
print(result.streams["supply"])
print(collect_flows(result))
