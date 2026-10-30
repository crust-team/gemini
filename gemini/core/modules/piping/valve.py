"""Control valve with an inherent flow characteristic and the IEC 60534 liquid sizing equation."""

from typing import Literal

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.types import (
    Control,
    FlowCoefficient,
    Fraction,
    Inlet,
    Outlet,
    Output,
    Parameter,
    PressureDifference,
    Ratio,
    Stream,
)
from gemini.errors import PhysicsRangeError
from gemini.ops import Constant

REFERENCE_DENSITY = Constant(
    "VALVE_REFERENCE_DENSITY",
    1000.0,
    "kg/m3",
    "reference water density rho_0 of the flow coefficient (IEC 60534-2-1)",
)


class Valve(Module):
    """Control valve throttling a liquid stream; isenthalpic, so the temperature is unchanged.

    Sizing equation for non-choked turbulent liquid flow (IEC 60534-2-1:2011, Industrial-process
    control valves, Part 2-1: Flow capacity, sizing equations for fluid flow under installed
    conditions) in SI form: ``q = Kv sqrt(dp rho_0 / rho)`` with ``q`` the volume flow [m3/s],
    ``rho_0 = 1000 kg/m3`` and ``Kv`` in m3/s/Pa^0.5 (a catalogue Kv in m3/h at 1 bar converts
    with the unit ``"m3/h/bar^0.5"``), so ``dp = rho / rho_0 (q / Kv_eff)^2``. The effective
    coefficient follows the theoretical inherent characteristic of IEC 60534-2-4 with
    ``Phi_0 = 1 / rangeability``: linear ``Phi = Phi_0 + (1 - Phi_0) h`` and equal percentage
    ``Phi = Phi_0 exp(h ln(1 / Phi_0)) = R^(h - 1)``, ``Kv_eff = Phi(h) flow_coefficient`` for an
    opening ``h > 0``. A real valve leaves this curve below ``Phi_0`` and seals at ``h = 0``,
    modelled as ``Kv_eff = 0``. The default characteristic is equal percentage, the most common
    one for process control valves, and the default rangeability 50 is the typical inherent
    rangeability of globe control valves (Emerson, Control Valve Handbook, 5th ed., 2017).

    Simplifications: no choked flow or cavitation (check the outlet pressure against the vapour
    pressure; IEC 60534-2-1 ``F_L`` limits are not modelled), no installed-characteristic or
    Reynolds-number correction, constant liquid density. The throttled pressure energy
    (``dp / (rho cp)``, about 0.024 K per bar for water) is not converted into a temperature
    rise, consistent with the package's sensible-enthalpy audit. Validity: single-phase liquid
    (free gas raises ``PhysicsRangeError``) in the marked flow direction (reverse flow raises
    ``PhysicsRangeError``). A closed valve passes zero flow with no pressure drop; flow through
    a closed valve raises ``PhysicsRangeError``.
    """

    def __init__(self):
        """Declare valve capacity, characteristic, opening and hydraulic outputs."""
        super().__init__()

        # Parameters
        self.flow_coefficient = Parameter(FlowCoefficient, gt=0)
        self.characteristic = Parameter(
            Literal["linear", "equal_percentage"], default="equal_percentage"
        )
        self.rangeability = Parameter(Ratio, default=50, gt=1)

        # Inlets
        self.inlet = Inlet(Stream)

        # Controls
        self.opening = Control(Fraction)

        # Outputs
        self.pressure_drop = Output(PressureDifference)
        self.effective_flow_coefficient = Output(FlowCoefficient)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Throttle the inlet stream by the sizing-equation pressure drop."""

        # Outlets
        inlet = inlets.inlet
        drop = self._pressure_drop(inlet)
        ops.check(
            drop <= inlet.p,
            PhysicsRangeError,
            "{path}: pressure drop = {drop} Pa; expected at most inlet.p = {inlet_p} Pa "
            "(open the valve or reduce the flow)",
            path=self.path,
            drop=drop,
            inlet_p=inlet.p,
        )
        outlet = inlet.with_(p=inlet.p - drop)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.pressure_drop = inlets.inlet.p - outlets.outlet.p
        self.effective_flow_coefficient = self._effective_flow_coefficient()

    def _effective_flow_coefficient(self):
        """Return the flow coefficient [m3/s/Pa^0.5] at the commanded opening."""
        floor = 1 / self.rangeability
        if self.characteristic == "linear":
            coefficient = self.flow_coefficient * (floor + (1 - floor) * self.opening)
        else:
            coefficient = self.flow_coefficient * self.rangeability ** (self.opening - 1)
        return ops.where(self.opening == 0, 0.0, coefficient)

    def _pressure_drop(self, inlet):
        """Return the pressure drop [Pa] of the inlet flow at the commanded opening."""
        ops.check(
            inlet.m_dot >= 0,
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0 (reverse flow is not modelled)",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        if inlet.fluid.gas_mass_fraction > 0:
            raise PhysicsRangeError(
                f"{self.path}: inlet.fluid.gas_mass_fraction = "
                f"{inlet.fluid.gas_mass_fraction}; expected 0 (single-phase liquid model)"
            )
        coefficient = self._effective_flow_coefficient()
        ops.check(
            ops.logical_or(inlet.m_dot == 0, coefficient != 0),
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s through a closed valve "
            "(opening = 0); expected zero flow",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        rho = inlet.fluid.properties(inlet.p, inlet.T).rho_l
        return ops.where(
            inlet.m_dot == 0,
            0.0,
            rho / REFERENCE_DENSITY * ops.truediv(inlet.m_dot / rho, coefficient) ** 2,
        )
