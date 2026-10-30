"""Fully mixed hot or chilled water storage tank with a charge and a discharge circuit."""

from typing import Literal

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.types import (
    Boundary,
    Energy,
    Fraction,
    HeatAbsorbed,
    HeatAccumulation,
    HeatLoss,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    State,
    Stream,
    Temperature,
    ThermalConductance,
    Volume,
)
from gemini.errors import PhysicsRangeError


class ThermalStorage(Module):
    """Fully mixed (lumped) hot or chilled water tank with charge and discharge circuits.

    The tank content is ``module.fluid`` at one uniform temperature, the state ``temperature``.
    Each circuit exchanges heat with the tank through a constant effectiveness ``e``
    (``charge_effectiveness``, ``discharge_effectiveness``); the default ``e = 1`` is a direct
    connection, where the circuit leaves at the tank temperature. With ``C_i = m_dot_i * cp_i``
    the heat flows into the tank are ``Q_i = e_i * C_i * (T_i_in - T)`` and the circuit leaves
    at ``T_i_out = T_i_in - e_i * (T_i_in - T)``; the ambient exchange is
    ``Q_amb = UA * (T - T_ambient)``. The tank balance (Duffie and Beckman 2013, *Solar
    Engineering of Thermal Processes*, 4th ed., section 8.3, fully mixed storage) is

        rho * cp * V * dT/dt = Q_charge + Q_discharge - Q_amb.

    ``_advance_states`` integrates it with its exact exponential solution over ``dt`` for inlets
    held constant during the step: with ``b = e_c C_c + e_d C_d + UA`` and the equilibrium
    ``T_eq = (e_c C_c T_c + e_d C_d T_d + UA T_ambient) / b``,
    ``T(dt) = T_eq + (T(0) - T_eq) * exp(-b dt / (rho cp V))``; it is unconditionally stable.
    Outlets and outputs use the start-of-step temperature.

    ``service`` sets the sign of the reported energies: a ``"hot"`` tank stores heat, so
    ``stored_energy = rho cp V (T - T_ref)``, ``charge_duty = Q_charge`` and ``discharge_duty =
    -Q_discharge``; a ``"chilled"`` tank stores cold, so every sign flips and ``stored_energy =
    rho cp V (T_ref - T)``. A negative duty means the circuit works against the service (for
    example charge water colder than a hot tank). ``Q_amb > 0`` is reported as ``heat_loss``,
    ``Q_amb < 0`` (a chilled tank in a warm room) as ``heat_absorbed``; the other one is zero.

    ``heat_accumulation`` is the rate of increase of the tank's sensible heat
    ``rho cp V dT/dt`` at the start of the step; ``energy_balance`` counts it as the signed
    storage outflow, so the tank is first-law closed. Each circuit keeps its mass flow, pressure
    and fluid (constant tank volume, no pressure loss), so ``mass_balance`` closes.

    Assumptions and validity: single-phase liquid below boiling, no thermal stratification
    (a stratified tank delivers hotter discharge water than this model), constant fluid
    properties at the start-of-step temperature, constant effectiveness independent of flow,
    and inlet temperatures constant over a step (use steps short against the tank time
    constant ``rho cp V / b`` when the inlets vary).

    NOTE(refactor): the tank temperature is a state, so the module is a graph break until
    ``scan`` exists; its arithmetic is written with ops all the same.
    """

    category = "storage"

    def __init__(self):
        """Declare tank design data, circuits, the tank temperature and its energies."""
        super().__init__()

        # Parameters
        self.service = Parameter(Literal["hot", "chilled"])
        self.volume = Parameter(Volume, gt=0)
        self.heat_loss_coefficient = Parameter(ThermalConductance)
        self.reference_temperature = Parameter(Temperature)
        self.charge_effectiveness = Parameter(Fraction, default=1)
        self.discharge_effectiveness = Parameter(Fraction, default=1)

        # Inlets
        self.charge_in = Inlet(Stream, stream="hot_water")
        self.discharge_in = Inlet(Stream, stream="hot_water")

        # Boundaries
        self.ambient_temperature = Boundary(Temperature)

        # States
        self.temperature = State(Temperature, default=293.15)

        # Outputs
        self.tank_temperature = Output(Temperature)
        self.stored_energy = Output(Energy)
        self.charge_duty = Output(Power)
        self.discharge_duty = Output(Power)
        self.heat_accumulation = Output(HeatAccumulation)
        self.heat_loss = Output(HeatLoss)
        self.heat_absorbed = Output(HeatAbsorbed)

        # Outlets
        self.charge_out = Outlet(Stream, stream="hot_water")
        self.discharge_out = Outlet(Stream, stream="hot_water")

    def forward(self, inlets):
        """Return both circuits after exchanging heat with the start-of-step tank."""

        # Outlets
        charge_in, discharge_in = inlets.charge_in, inlets.discharge_in
        charge_T = self._outlet_temperature(charge_in, self.charge_effectiveness)
        discharge_T = self._outlet_temperature(discharge_in, self.discharge_effectiveness)
        charge_out = charge_in.with_(T=charge_T)
        discharge_out = discharge_in.with_(T=discharge_T)

        outlets = dict(charge_out=charge_out, discharge_out=discharge_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        sign = 1 if self.service == "hot" else -1
        charge = self._circuit_heat(inlets.charge_in, self.charge_effectiveness)
        discharge = self._circuit_heat(inlets.discharge_in, self.discharge_effectiveness)
        ambient = self.heat_loss_coefficient * (self.temperature - self.ambient_temperature)
        self.tank_temperature = self.temperature
        self.stored_energy = (
            sign
            * self._capacity(inlets.charge_in)
            * (self.temperature - self.reference_temperature)
        )
        self.charge_duty = sign * charge
        self.discharge_duty = -sign * discharge
        self.heat_accumulation = charge + discharge - ambient
        self.heat_loss = ops.maximum(ambient, 0.0)
        self.heat_absorbed = ops.maximum(-ambient, 0.0)

    def _advance_states(self, inlets, outlets, dt):
        terms = [
            (self._conductance(inlets.charge_in, self.charge_effectiveness), inlets.charge_in.T),
            (
                self._conductance(inlets.discharge_in, self.discharge_effectiveness),
                inlets.discharge_in.T,
            ),
            (self.heat_loss_coefficient, self.ambient_temperature),
        ]
        total = sum(conductance for conductance, _ in terms)
        weighted = sum(conductance * temperature for conductance, temperature in terms)
        equilibrium = weighted / total
        decay = ops.exp(-total * dt / self._capacity(inlets.charge_in))
        relaxed = equilibrium + (self.temperature - equilibrium) * decay
        return {"temperature": ops.where(total == 0, self.temperature, relaxed)}

    def _capacity(self, charge_in):
        """Return the tank heat capacity rho * cp * V [J/K] of ``module.fluid``."""
        properties = self.fluid.properties(charge_in.p, self.temperature)
        return properties.liquid_volumetric_heat_capacity * self.volume

    def _conductance(self, stream, effectiveness):
        """Return the circuit conductance e * m_dot * cp [W/K]; reject reverse flow."""
        ops.check(
            stream.m_dot >= 0,
            PhysicsRangeError,
            "{path}: circuit m_dot = {m_dot} kg/s; expected >= 0 (reverse flow " "is not modelled)",
            path=self.path,
            m_dot=stream.m_dot,
        )
        return effectiveness * stream.m_dot * stream.fluid.properties(stream.p, stream.T).cp_l

    def _circuit_heat(self, stream, effectiveness):
        """Return the heat flow [W] from a circuit into the start-of-step tank."""
        return self._conductance(stream, effectiveness) * (stream.T - self.temperature)

    def _outlet_temperature(self, stream, effectiveness):
        """Return a circuit's outlet temperature [K]; a stopped circuit keeps its inlet value."""
        return ops.where(
            self._conductance(stream, effectiveness) == 0,
            stream.T,
            stream.T - effectiveness * (stream.T - self.temperature),
        )
