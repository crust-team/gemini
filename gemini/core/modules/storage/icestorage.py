"""Lumped ice-on-coil or encapsulated ice store on one glycol circuit."""

import math

from gemini.core.modules.module import Module
from gemini.core.physics import heat_transfer
from gemini.core.types import (
    Energy,
    Fraction,
    Inlet,
    Mass,
    Outlet,
    Output,
    Parameter,
    Power,
    SpecificEnthalpy,
    SpecificHeat,
    State,
    Stream,
    Temperature,
    ThermalConductance,
)
from gemini.errors import ConfigurationError, PhysicsRangeError

MAX_SEGMENTS = 3
"""Most phase segments one step can cross: liquid, freezing or melting, then solid (or back)."""


class IceStorage(Module):
    """Lumped ice store for cooling: a glycol coil freezes or melts a fixed mass of water.

    The store holds ``water_mass`` M of water at one uniform temperature T, of which the
    state ``ice_fraction`` x is frozen. The state ``temperature`` is the store temperature: the
    freezing temperature T_f while partly frozen (0 < x < 1), above it only as all liquid
    (x = 0, sensible heat with ``water_heat_capacity``) and below it only as all ice (x = 1,
    sensible heat with ``ice_heat_capacity``). Other combinations raise ``ConfigurationError``.

    The coil is a heat exchanger against a store at uniform temperature (capacity ratio zero),
    so with ``C = m_dot * cp`` of the glycol its effectiveness is ``e = 1 - exp(-UA / C)``
    (Incropera et al., *Fundamentals of Heat and Mass Transfer*, effectiveness-NTU method). The
    heat flow from the glycol into the store is ``duty = e * C * (T_in - T)`` and the glycol
    leaves at ``outlet_T = T_in - e * (T_in - T)``. A glycol inlet below T_f charges the store
    (negative duty: water freezes, then the ice subcools), one above T_f discharges it (positive
    duty: the store cools the glycol, the ice melts, then the water warms).

    ``_advance_states`` integrates the enthalpy balance exactly and piecewise over ``dt`` for an
    inlet held constant during the step: in the latent segment T = T_f and the duty is constant,
    so x changes linearly by ``-duty * t / (M * L)``; in a sensible segment T relaxes towards
    ``T_in`` with the time constant ``M * c / (e * C)``. A step moves to the next segment when
    the store becomes full (x = 1) or empty (x = 0), or reaches T_f, so it can cross at most
    three segments. Outlets and outputs use the start-of-step state.

    ``stored_cold = M * L * x`` is the latent cold available. The store is perfectly insulated
    and the coil carries the glycol in a closed circuit, so ``mass_balance`` closes.
    ``heat_accumulation`` equals ``duty``, the rate of increase of the store's internal energy
    at the start of the step (negative while charging with cold); ``energy_balance`` counts it as
    the signed storage outflow, so the store is first-law closed.

    Defaults: ``latent_heat`` 333.55 kJ/kg is the conventional latent heat of fusion of ice at
    0 degC and 101.325 kPa; IAPWS R10-06 (Feistel and Wagner 2006, *A new equation of state for
    H2O ice Ih*) gives 333.44 kJ/kg at the triple point, 0.03 % lower. ``freezing_temperature``
    273.15 K is the normal melting point. ``water_heat_capacity`` 4219.9 J/kg/K is saturated
    liquid water at 0.01 degC (IAPWS-95, Wagner and Pruss 2002) and ``ice_heat_capacity``
    2096.8 J/kg/K is ice Ih at the triple point (IAPWS R10-06).

    Simplifications and validity: one lumped store temperature, constant coil UA (in a real
    ice-on-coil store UA falls as the ice layer thickens and depends on the glycol flow regime;
    ASHRAE Handbook, HVAC Applications, chapter Thermal Storage), constant properties, no
    supercooling or nucleation delay, no ambient heat gain and no pressure loss. Suitable for
    hourly or 15-minute dispatch studies of the store's state of charge, not for coil design.
    """

    def __init__(self):
        """Declare store design data, the glycol circuit, the phase state and its energies."""
        super().__init__()

        # Parameters
        self.water_mass = Parameter(Mass, gt=0)
        self.ua = Parameter(ThermalConductance, gt=0)
        self.latent_heat = Parameter(SpecificEnthalpy, default=333550, gt=0)
        self.freezing_temperature = Parameter(Temperature, default=273.15)
        self.water_heat_capacity = Parameter(SpecificHeat, default=4219.9)
        self.ice_heat_capacity = Parameter(SpecificHeat, default=2096.8)

        # Inlets
        self.inlet = Inlet(Stream)

        # States
        self.ice_fraction = State(Fraction, default=0)
        self.temperature = State(Temperature, default=273.15)

        # Outputs
        self.stored_cold = Output(Energy)
        self.duty = Output(Power)
        self.heat_accumulation = Output(Power)
        self.outlet_T = Output(Temperature)
        self.is_full = Output(bool)
        self.is_empty = Output(bool)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Return the glycol after exchanging heat with the start-of-step store."""

        # Outlets
        inlet = inlets.inlet
        effectiveness = self._effectiveness(inlet)
        outlet = inlet.with_(T=inlet.T - effectiveness * (inlet.T - self.temperature))

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        self.stored_cold = self.water_mass * self.latent_heat * self.ice_fraction
        self.duty = self._conductance(inlet) * (inlet.T - self.temperature)
        self.heat_accumulation = self.duty
        self.outlet_T = outlets.outlet.T
        self.is_full = self.ice_fraction >= 1
        self.is_empty = self.ice_fraction <= 0

    def _advance_states(self, inlets, outlets, dt):
        inlet = inlets.inlet
        conductance = self._conductance(inlet)
        fraction, temperature, remaining = self.ice_fraction, self.temperature, dt
        for _ in range(MAX_SEGMENTS):
            if remaining <= 0 or conductance == 0:
                break
            fraction, temperature, remaining = self._segment(
                fraction, temperature, inlet.T, conductance, remaining
            )
        return {"ice_fraction": fraction, "temperature": temperature}

    def _rate(self, inlet):
        """Return the glycol capacity rate m_dot * cp [W/K]; reject reverse flow."""
        if inlet.m_dot < 0:
            raise PhysicsRangeError(
                f"{self.path}: inlet.m_dot = {inlet.m_dot} kg/s; expected >= 0 (reverse flow is "
                "not modelled)"
            )
        return inlet.m_dot * inlet.fluid.properties(inlet.p, inlet.T).cp_l

    def _effectiveness(self, inlet):
        """Return the coil effectiveness 1 - exp(-UA / C) [-] after checking the store state."""
        self._check_state()
        rate = self._rate(inlet)
        if rate == 0:
            return 0.0
        return heat_transfer.effectiveness_counterflow(heat_transfer.ntu(self.ua, rate), 0)

    def _conductance(self, inlet):
        """Return the coil conductance e * m_dot * cp [W/K]."""
        return self._effectiveness(inlet) * self._rate(inlet)

    def _check_state(self):
        """Require the store temperature to match its phase (see the class docstring)."""
        fraction, temperature = self.ice_fraction, self.temperature
        freezing = self.freezing_temperature
        consistent = (
            temperature == freezing
            or (fraction == 0 and temperature > freezing)
            or (fraction == 1 and temperature < freezing)
        )
        if not consistent:
            raise ConfigurationError(
                f"{self.path}: temperature = {temperature} K with ice_fraction = {fraction}; "
                f"expected {freezing} K while partly frozen, above it only with no ice and "
                "below it only when fully frozen"
            )

    def _segment(self, fraction, temperature, inlet_T, conductance, duration):
        """Advance one phase segment; return the fraction, temperature and time left [s]."""
        freezing = self.freezing_temperature
        if temperature > freezing or (fraction == 0 and inlet_T > freezing):
            capacity = self.water_mass * self.water_heat_capacity
            return self._sensible(fraction, temperature, inlet_T, capacity / conductance, duration)
        if temperature < freezing or (fraction == 1 and inlet_T < freezing):
            capacity = self.water_mass * self.ice_heat_capacity
            return self._sensible(fraction, temperature, inlet_T, capacity / conductance, duration)
        return self._latent(fraction, conductance * (inlet_T - freezing), duration)

    def _sensible(self, fraction, temperature, inlet_T, time_constant, duration):
        """Relax an all-liquid or all-ice store towards the inlet, stopping at freezing."""
        freezing = self.freezing_temperature
        crosses = (temperature - freezing) * (inlet_T - freezing) < 0
        if crosses:
            reach = time_constant * math.log((temperature - inlet_T) / (freezing - inlet_T))
            if reach < duration:
                return fraction, freezing, duration - reach
        relaxed = inlet_T + (temperature - inlet_T) * math.exp(-duration / time_constant)
        if crosses and (relaxed - freezing) * (temperature - freezing) <= 0:
            relaxed = freezing
        return fraction, relaxed, 0.0

    def _latent(self, fraction, heat, duration):
        """Freeze (heat < 0) or melt (heat > 0) at constant duty until full, empty or done."""
        freezing = self.freezing_temperature
        if heat == 0:
            return fraction, freezing, 0.0
        latent_capacity = self.water_mass * self.latent_heat
        target = 0.0 if heat > 0 else 1.0
        reach = latent_capacity * abs(target - fraction) / abs(heat)
        if reach < duration:
            return target, freezing, duration - reach
        changed = fraction - heat * duration / latent_capacity
        return min(1.0, max(0.0, changed)), freezing, 0.0
