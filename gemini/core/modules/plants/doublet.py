"""Reusable production and reinjection limbs of a geothermal doublet."""

from pydantic import BaseModel, ConfigDict, Field

from gemini.core.modules.module import Module
from gemini.core.types import HeatFlow, ModuleResult, PowerFlow, Stream
from gemini.core.types.quantities import Frequency, MassFlow


class Doublet(Module):
    """Produce hot supply and return cooled brine to the receiving aquifer.

    `produce` and `inject` expose the two independent limbs for plants whose
    surface equipment connects supply to return during the same evaluation.
    They invoke all equipment through __call__, preserving leaf hooks and audits.
    """

    name = "doublet"
    category = "plant"
    description = "Explicit geothermal production and reinjection paths."
    inlets = {"return": Stream}
    outlets = {"supply": Stream, "electricity": PowerFlow, "heat_loss": HeatFlow}

    class Inputs(BaseModel):
        """Production controls; reinjection conditions arrive through the return stream."""

        model_config = ConfigDict(extra="forbid")
        m_dot: MassFlow = Field(ge=0, description="Production rate [kg/s]")
        esp_frequency: Frequency = Field(description="ESP drive frequency [Hz]")

    def __init__(self, reservoir, well, esp, riser, injector, sink):
        """Register explicitly supplied equipment, including both sides of the buried ESP."""
        super().__init__()
        self.reservoir = reservoir
        self.well = well
        self.esp = esp
        self.riser = riser
        self.injector = injector
        self.sink = sink

    @classmethod
    def from_config(cls, config, at=None):
        """Build named equipment from a Doublet configuration without reading any wiring."""
        from gemini.core.modules.catalogue import create

        expected = {"reservoir", "well", "esp", "riser", "injector", "sink"}
        if set(config.modules) != expected:
            raise ValueError(f"Doublet requires exactly {sorted(expected)}")
        return cls(
            **{
                name: create(item.type, item.at(at).params, fluid=item.fluid)
                for name, item in config.modules.items()
            }
        )

    def produce(self, inputs):
        """Traverse reservoir, lower well, ESP and riser, returning supply and energy reports."""
        inputs = self.Inputs.model_validate(inputs)
        source = self.reservoir({"m_dot": inputs.m_dot})
        lower = self.well(bottom=source.streams["sandface"])
        pump = self.esp({"frequency": inputs.esp_frequency}, suction=lower.streams["wellhead"])
        upper = self.riser(bottom=pump.streams["discharge"])
        return (
            upper.streams["wellhead"],
            pump.streams["electricity"],
            HeatFlow(Q=lower.streams["heat_loss"].Q + upper.streams["heat_loss"].Q),
        )

    def inject(self, stream):
        """Traverse the injection well and deliver its bottom stream to the receiving aquifer."""
        injection = self.injector(wellhead=stream)
        self.sink(sandface=injection.streams["bottom"])
        return injection.streams["heat_loss"]

    def forward(self, inputs, streams_in):
        """Evaluate both limbs for an independently specified return boundary."""
        supply, electricity, heat = self.produce(inputs)
        rejected = self.inject(streams_in["return"])
        return ModuleResult(
            self.Outputs(),
            {
                "supply": supply,
                "electricity": electricity,
                "heat_loss": HeatFlow(Q=heat.Q + rejected.Q),
            },
        )
