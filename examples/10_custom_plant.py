"""Define and run a custom plant with a doublet, heat exchanger and auxiliary boiler."""

from pathlib import Path

from pydantic import Field

import gemini as gm
from gemini.core.types import ModuleResult
from gemini.core.types.quantities import Temperature


class HeatingPlant(gm.modules.Module):
    """A user-defined plant: child assignment registers it, forward defines its wiring."""

    name, category = "custom_heating", "plant"
    outlets = {"supply": gm.Stream}

    class Inputs(gm.plants.Doublet.Inputs):
        """Production controls, secondary inlet and heating target."""

        secondary: gm.Stream = Field(description="Heating return [-]")
        target: Temperature = Field(description="Heating supply temperature [K]")

    def __init__(self, doublet, exchanger):
        """Compose reusable equipment with a local auxiliary heat source."""
        super().__init__()
        self.doublet, self.exchanger = doublet, exchanger
        self.boiler = gm.modules.Boiler(dict(fuel="electric", capacity=1e6, efficiency=0.98))

    def forward(self, inputs, streams_in):
        """Connect geothermal production, heat transfer, reinjection and auxiliary heating."""
        hot, _, _ = self.doublet.produce(
            dict(m_dot=inputs.m_dot, esp_frequency=inputs.esp_frequency)
        )
        hx = self.exchanger(hot_in=hot, cold_in=inputs.secondary)
        self.doublet.inject(hx.streams["hot_out"])
        heated = self.boiler(dict(setpoint_T=inputs.target), inlet=hx.streams["cold_out"])
        return ModuleResult(self.Outputs(), {"supply": heated.streams["outlet"]})


base = gm.load_plant(Path(__file__).parents[1] / "datasets/geothermal_doublet")
plant = HeatingPlant(base.doublet, base.heat_exchanger)
result = plant(
    dict(
        m_dot=40,
        esp_frequency=60,
        target=340,
        secondary=gm.Stream(m_dot=40, T=300, p=5e5, fluid=gm.WATER),
    )
)
print(result.streams["supply"])
print(gm.modules.collect_flows(result))
