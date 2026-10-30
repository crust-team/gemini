"""Vent stack or flare disposing of separated non-condensable gas."""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.physics import constants
from gemini.core.types import (
    Efficiency,
    Fraction,
    Fuel,
    HeatLoss,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    SpecificEnthalpy,
    Stream,
)
from gemini.errors import ConfigurationError, PhysicsRangeError

METHANE_MOLAR_MASS = 0.016043
"""Molar mass of methane [kg/mol] (IUPAC 2013 standard atomic weights)."""

METHANE_HEATING_VALUE = 50.0e6
"""Lower heating value of methane [J/kg]: 802.3 kJ/mol (NIST Chemistry WebBook) / 16.043 g/mol."""

FLARE_EFFICIENCY = 0.98
"""Combustion (destruction) efficiency of a well-operated flare [-] (US EPA AP-42, 13.5)."""


class Vent(Module):
    """Vent stack or flare releasing separated gas from the plant, with CO2 and methane emissions.

    The gas is a mixture of CO2 (``co2_mass_fraction``), methane (``methane_mass_fraction``, the
    combustible part, treated as methane for stoichiometry and heating value) and inert or
    unaccounted rest (N2, H2S, water vapour), all as mass fractions of the gas, which a
    gas analysis gives. ``mode="vent"`` releases it unburnt; ``mode="flare"`` burns the
    methane with ``combustion_efficiency``, CH4 + 2 O2 -> CO2 + 2 H2O:

    - ``vented_mass_flow = inlet.m_dot`` (the gas mass flow, see ``Degasser.gas``);
    - burnt methane ``m_b = combustion_efficiency * x_CH4 * m_dot`` when flaring, else 0;
    - ``co2_emission = x_CO2 * m_dot + m_b * M_CO2 / M_CH4``;
    - ``methane_emission = x_CH4 * m_dot - m_b``;
    - ``fuel = heat_loss = m_b * heating_value``: the chemical energy of the burnt gas is a
      fuel input and its combustion heat is lost to the air, so the audit closes exactly.

    Sources: flare destruction efficiency 98 % (US EPA, AP-42, 5th ed., section 13.5
    "Industrial Flares", 2018); methane lower heating value 50.0 MJ/kg (NIST Chemistry
    WebBook). Burning H2S to SO2 and other combustibles is not modelled.

    The ``outlet`` is the gas as it is released at the stack or flare tip, upstream of
    combustion: inlet mass flow, temperature, pressure and fluid unchanged. Leaving the plant
    through a port keeps ``mass_balance`` and ``energy_balance`` honest without a special
    boundary case; the combustion products and air are not streams. Reverse flow raises
    ``PhysicsRangeError``.
    """

    def __init__(self):
        """Declare gas composition, disposal mode, ports and emissions."""
        super().__init__()

        # Parameters
        self.mode = Parameter(Literal["vent", "flare"])
        self.co2_mass_fraction = Parameter(Fraction)
        self.methane_mass_fraction = Parameter(Fraction, default=0)
        self.heating_value = Parameter(SpecificEnthalpy, default=METHANE_HEATING_VALUE, ge=0)
        self.combustion_efficiency = Parameter(Efficiency, default=FLARE_EFFICIENCY)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.vented_mass_flow = Output(MassFlow)
        self.co2_emission = Output(MassFlow)
        self.methane_emission = Output(MassFlow)
        self.fuel = Output(Fuel)
        self.heat_loss = Output(HeatLoss)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Release the gas from the plant unchanged."""

        # Outlets
        inlet = inlets.inlet
        self._check(inlet)
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        gas_flow = inlets.inlet.m_dot
        methane = self.methane_mass_fraction * gas_flow
        burnt = self.combustion_efficiency * methane if self.mode == "flare" else 0.0
        self.vented_mass_flow = gas_flow
        self.co2_emission = (
            self.co2_mass_fraction * gas_flow
            + burnt * constants.CO2_MOLAR_MASS / METHANE_MOLAR_MASS
        )
        self.methane_emission = methane - burnt
        self.fuel = burnt * self.heating_value
        self.heat_loss = self.fuel

    def _check(self, inlet):
        """Reject reverse flow and gas compositions above one."""
        if inlet.m_dot < 0:
            raise PhysicsRangeError(f"{self.path}: inlet.m_dot = {inlet.m_dot} kg/s; expected >= 0")
        total = self.co2_mass_fraction + self.methane_mass_fraction
        if total > 1:
            raise ConfigurationError(
                f"{self.path}: co2_mass_fraction + methane_mass_fraction = {total}; "
                "expected at most 1"
            )
