"""Lumped ice-on-coil or encapsulated ice store on one glycol circuit."""

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.physics import heat_transfer
from gemini.core.types import (
    Duty,
    Energy,
    Fraction,
    HeatAccumulation,
    Inlet,
    Mass,
    Outlet,
    Output,
    Parameter,
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

    NOTE(refactor): the ice fraction and the temperature are states, so the module is a graph
    break until ``scan`` exists; its arithmetic is written with ops all the same, and the segment
    loop of ``_advance_states`` runs its fixed ``MAX_SEGMENTS`` passes, a finished pass keeping
    its state.
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
        self.duty = Output(Duty)
        self.heat_accumulation = Output(HeatAccumulation)
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
        state = (self.ice_fraction, self.temperature, dt)
        for _ in range(MAX_SEGMENTS):
            finished = ops.logical_or(state[2] <= 0, conductance == 0)
            advanced = self._segment(*state, inlet.T, conductance)
            state = self._select(finished, state, advanced)
        fraction, temperature, _ = state
        return {"ice_fraction": fraction, "temperature": temperature}

    @staticmethod
    def _select(condition, if_true, if_false):
        """Return the tuple of ``if_true`` where ``condition`` holds, else of ``if_false``."""
        return tuple(ops.where(condition, a, b) for a, b in zip(if_true, if_false))

    def _rate(self, inlet):
        """Return the glycol capacity rate m_dot * cp [W/K]; reject reverse flow."""
        ops.check(
            inlet.m_dot >= 0,
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0 (reverse flow is not modelled)",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        return inlet.m_dot * inlet.fluid.properties(inlet.p, inlet.T).cp_l

    def _effectiveness(self, inlet):
        """Return the coil effectiveness 1 - exp(-UA / C) [-] after checking the store state."""
        self._check_state()
        rate = self._rate(inlet)
        transfer_units = heat_transfer.ntu(self.ua, ops.where(rate == 0, 1.0, rate))
        return ops.where(rate == 0, 0.0, heat_transfer.effectiveness_counterflow(transfer_units, 0))

    def _conductance(self, inlet):
        """Return the coil conductance e * m_dot * cp [W/K]."""
        return self._effectiveness(inlet) * self._rate(inlet)

    def _check_state(self):
        """Require the store temperature to match its phase (see the class docstring)."""
        fraction, temperature = self.ice_fraction, self.temperature
        freezing = self.freezing_temperature
        consistent = ops.logical_or(
            ops.logical_or(
                temperature == freezing,
                ops.logical_and(fraction == 0, temperature > freezing),
            ),
            ops.logical_and(fraction == 1, temperature < freezing),
        )
        ops.check(
            consistent,
            ConfigurationError,
            "{path}: temperature = {temperature} K with ice_fraction = {fraction}; "
            "expected {freezing} K while partly frozen, above it only with no ice and "
            "below it only when fully frozen",
            path=self.path,
            temperature=temperature,
            fraction=fraction,
            freezing=freezing,
        )

    def _segment(self, fraction, temperature, duration, inlet_T, conductance):
        """Advance one phase segment; return the fraction, temperature and time left [s]."""
        freezing = self.freezing_temperature
        liquid = ops.logical_or(
            temperature > freezing, ops.logical_and(fraction == 0, inlet_T > freezing)
        )
        solid = ops.logical_or(
            temperature < freezing, ops.logical_and(fraction == 1, inlet_T < freezing)
        )
        water = self.water_mass * self.water_heat_capacity
        ice = self.water_mass * self.ice_heat_capacity
        args = (fraction, temperature, inlet_T)
        return self._select(
            liquid,
            self._sensible(*args, ops.truediv(water, conductance), duration),
            self._select(
                solid,
                self._sensible(*args, ops.truediv(ice, conductance), duration),
                self._latent(fraction, conductance * (inlet_T - freezing), duration),
            ),
        )

    def _sensible(self, fraction, temperature, inlet_T, time_constant, duration):
        """Relax an all-liquid or all-ice store towards the inlet, stopping at freezing."""
        freezing = self.freezing_temperature
        crosses = (temperature - freezing) * (inlet_T - freezing) < 0
        reach = time_constant * ops.log(ops.truediv(temperature - inlet_T, freezing - inlet_T))
        stops = ops.logical_and(crosses, reach < duration)
        relaxed = inlet_T + (temperature - inlet_T) * ops.exp(-duration / time_constant)
        overshoots = ops.logical_and(crosses, (relaxed - freezing) * (temperature - freezing) <= 0)
        return (
            fraction,
            ops.where(ops.logical_or(stops, overshoots), freezing, relaxed),
            ops.where(stops, duration - reach, 0.0),
        )

    def _latent(self, fraction, heat, duration):
        """Freeze (heat < 0) or melt (heat > 0) at constant duty until full, empty or done."""
        freezing = self.freezing_temperature
        latent_capacity = self.water_mass * self.latent_heat
        target = ops.where(heat > 0, 0.0, 1.0)
        reach = ops.truediv(latent_capacity * ops.abs(target - fraction), ops.abs(heat))
        changed = fraction - heat * duration / latent_capacity
        reached = reach < duration
        moved = (
            ops.where(reached, target, ops.minimum(1.0, ops.maximum(0.0, changed))),
            freezing,
            ops.where(reached, duration - reach, 0.0),
        )
        return self._select(heat == 0, (fraction, freezing, 0.0), moved)
