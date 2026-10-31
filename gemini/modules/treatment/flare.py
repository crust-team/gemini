"""Flare that burns the gas reaching it and reports what it emits."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules.module import Module
from gemini.physics import combustion, gas
from gemini.types import Efficiency, Inlet, MassFlow, Output, Parameter, Stream
from gemini.types.cost import scaled_cost


class Flare(Module):
    """Flare burning its inlet gas, with the CO2 and methane its composition gives.

    ``co2_emission`` is the CO2 the gas carries plus what burning forms and ``methane_emission`` the
    methane that passes unburnt; ``combustion_efficiency`` defaults to 98 % (US EPA, AP-42, 5th
    ed., section 13.5 "Industrial Flares", 2018). The gas leaves the plant here, so the flare has no
    outlet; ``burned_mass_flow`` closes ``mass_balance``. A ``Vent`` with ``mode="flare"`` takes
    mass fractions as parameters; this module reads the composition of the stream and suits the
    gas of a ``Degasser``.
    """

    def __init__(self):
        """Declare the efficiency, the inlet and the emissions."""
        super().__init__()

        # Parameters
        self.combustion_efficiency = Parameter(Efficiency, default=combustion.FLARE_EFFICIENCY)

        # Inlets
        self.gas_in = Inlet(Stream, kind="gas")

        # Outputs
        self.burned_mass_flow = Output(MassFlow)
        self.co2_emission = Output(MassFlow)
        self.methane_emission = Output(MassFlow)

    def forward(self, inlets):
        """Refuse reverse flow; the flare has no outlet."""
        ops.check(
            inlets.gas_in.m_dot >= 0,
            PhysicsError,
            "{path}: gas_in.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlets.gas_in.m_dot,
        )
        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.gas_in
        composition = inlet.fluid.gas_composition or {}
        carried, formed, methane = 0.0, 0.0, 0.0
        if composition:
            carried = gas.mass_fraction(composition, "CO2")
            formed = gas.combustion_co2(composition)
            methane = gas.mass_fraction(composition, "CH4")
        self.burned_mass_flow = inlet.m_dot
        self.co2_emission, self.methane_emission = combustion.burnt_gas_emissions(
            inlet.m_dot, carried, formed, methane, self.combustion_efficiency
        )

    def capex(self, assumptions):
        """Return the cost of the flare, a fixed item."""
        return scaled_cost(assumptions, "flare_cost")
