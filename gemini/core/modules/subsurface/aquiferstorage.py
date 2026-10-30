"""Aquifer thermal energy storage (ATES) well pair with a warm and a cold store."""

from typing import Literal

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.physics import ground
from gemini.core.types import (
    Control,
    Dimensionless,
    Duration,
    Energy,
    Fraction,
    HeatAbsorbed,
    HeatAccumulation,
    HeatLoss,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    State,
    Stream,
    Temperature,
    TemperatureDifference,
    ThermalConductivity,
    Volume,
    VolumetricHeatCapacity,
)
from gemini.errors import PhysicsRangeError

HALF_YEAR = 182.625 * 24 * 3600
"""Default storage period [s]: one charge or discharge season of seasonal ATES."""

STORES = ("warm", "cold")
"""The two stores of the well pair, in state order."""

SOURCE_AND_TARGET = {"charge": ("cold", "warm"), "discharge": ("warm", "cold")}
"""Store produced from and store injected into, per flowing ``mode``."""


class AquiferStorage(Module):
    """Balanced ATES well pair storing heat in a warm and cold in a cold aquifer store.

    ``mode`` ``"charge"`` produces from the cold well and injects ``injection_in`` into the
    warm well (summer: heat from cooling is stored); ``"discharge"`` produces from the warm
    well and injects into the cold well (winter: stored heat is recovered); ``"idle"`` moves no
    water and requires zero flow. The doublet is balanced: ``production_out`` carries the
    injected mass flow, pressure and fluid at the temperature of the store it is produced from
    (the aquifer temperature in idle mode); well hydraulics belong to well modules.

    Each store is fully mixed and described by its injected water volume V [m3] and its
    temperature change theta = T - T_aq [K] relative to ``aquifer_temperature``; an empty
    store produces native groundwater at the aquifer temperature. Its excess heat is
    E = (rho c)_w V theta, with (rho c)_w from the circuit fluid, and it occupies the thermal
    volume V (rho c)_w / (rho c)_a with (rho c)_a = phi (rho c)_w + (1 - phi) (rho c)_r, a
    cylinder of height ``aquifer_thickness`` H and thermal radius R. Losses to the
    surroundings are transient conduction through the whole envelope A = 2 pi R (R + H),
    averaged over the ``storage_period`` t_p: UA = 2 k A / sqrt(pi alpha t_p) with
    alpha = k / (rho c)_a (``ground.cylinder_store_conductance``, Carslaw and Jaeger 1959), so
    each store relaxes towards the aquifer temperature with the time constant
    (rho c)_w V / UA and the losses scale with the area-to-volume ratio, as observed for ATES
    (Bloemendal and Hartog 2018, Geothermics 71, 306-319). A store above the aquifer
    temperature reports its loss as ``heat_loss``, one below it its gain as
    ``heat_absorbed``. The default ``storage_period`` is half a year, the charge or discharge
    season of seasonal ATES.

    Each step first applies the injected volume Q dt (mixing) and the withdrawn volume
    (temperature unchanged; the store volume stops at zero, after which native water is
    produced), then the exact exponential conduction decay over ``dt`` at the end-of-step
    volume. The decay is exact for an idle store; with flow the operator splitting is first
    order in ``dt``. When a store empties within one step, the step's production temperature
    is still the start-of-step store temperature.

    ``stored_energy`` is the net excess heat of both stores (the cold store counts negative).
    ``recovery_efficiency`` is the warm store's thermal recovery, heat produced over heat
    injected, both relative to the aquifer temperature (the definition of Bloemendal and
    Hartog 2018); it is ``None`` until positive heat has been charged.

    Assumptions: no regional groundwater flow, dispersion or buoyancy; no thermal
    interaction between the wells; a sharp, fully mixed store instead of a thermal fringe
    (late-season production temperatures are therefore too high and early ones too low); a
    fully penetrating screen over H; and a conduction boundary layer sqrt(alpha t_p) thin
    against R and H. Dispersion and fringe losses are not resolved, so
    ``ground_conductivity`` is calibratable as an effective value. Valid for low-temperature
    ATES (stores below about 30 degC, so buoyancy flow is weak).
    ``heat_accumulation`` is the rate of change of the stored heat at the start of the step: the
    sensible enthalpy flow of ``injection_in`` minus that of ``production_out`` (``m_dot cp T``
    per stream, the basis of ``energy_balance``) minus the net conduction loss. It is the signed
    storage outflow of ``energy_balance``, so the well pair is first-law closed per call.

    The production temperature does not depend on the injected stream, so a plant that closes
    the groundwater loop through this module (production, pump, heat exchanger, injection)
    reads it first with ``production_temperature()`` and then calls the module once with the
    returned groundwater.

    NOTE(refactor): written with ops, but a graph break while the graph has no ``scan``: the
    store volumes, temperature changes and heat totals are states.
    """

    def __init__(self):
        """Declare aquifer data, the operating mode and the two store states."""
        super().__init__()

        # Parameters
        self.aquifer_temperature = Parameter(Temperature)
        self.aquifer_thickness = Parameter(Length, gt=0)
        self.porosity = Parameter(Fraction, gt=0, lt=1)
        self.rock_volumetric_heat_capacity = Parameter(VolumetricHeatCapacity)
        self.ground_conductivity = Parameter(ThermalConductivity, calibratable=True)
        self.storage_period = Parameter(Duration, default=HALF_YEAR, gt=0)

        # Inlets
        self.injection_in = Inlet(Stream)

        # Controls
        self.mode = Control(Literal["charge", "discharge", "idle"])

        # States
        self.warm_volume = State(Volume, default=0)
        self.warm_temperature_change = State(TemperatureDifference, default=0)
        self.cold_volume = State(Volume, default=0)
        self.cold_temperature_change = State(TemperatureDifference, default=0)
        self.charged_heat = State(Energy, default=0)
        self.recovered_heat = State(Energy, default=0)

        # Outputs
        self.stored_energy = Output(Energy)
        self.production_T = Output(Temperature)
        self.recovery_efficiency = Output(Dimensionless | None)
        self.warm_temperature = Output(Temperature)
        self.cold_temperature = Output(Temperature)
        self.heat_loss = Output(HeatLoss)
        self.heat_absorbed = Output(HeatAbsorbed)
        self.heat_accumulation = Output(HeatAccumulation)

        # Outlets
        self.production_out = Outlet(Stream)

    def forward(self, inlets):
        """Produce the injected mass flow from the source store of the current mode."""

        # Outlets
        injection_in = inlets.injection_in
        self._volume_flow(injection_in)
        production_out = injection_in.with_(T=self._production_temperature(self._start_states()))

        outlets = dict(production_out=production_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        fluid = self._fluid_heat_capacity(inlets.injection_in)
        losses = [
            self._store_conductance(self._volume(store), inlets.injection_in) * self._change(store)
            for store in STORES
        ]
        stored = sum(self._volume(store) * self._change(store) for store in STORES)
        self.stored_energy = fluid * stored
        self.production_T = outlets.production_out.T
        charged = self.charged_heat
        self.recovery_efficiency = ops.where(
            charged > 0, ops.truediv(self.recovered_heat, charged), None
        )
        self.warm_temperature = self.aquifer_temperature + self.warm_temperature_change
        self.cold_temperature = self.aquifer_temperature + self.cold_temperature_change
        self.heat_loss = sum(ops.maximum(loss, 0) for loss in losses)
        self.heat_absorbed = sum(ops.maximum(-loss, 0) for loss in losses)
        self.heat_accumulation = (
            _enthalpy_flow(inlets.injection_in)
            - _enthalpy_flow(outlets.production_out)
            - sum(losses)
        )

    def _advance_states(self, inlets, outlets, dt):
        injection = inlets.injection_in
        volume = self._volume_flow(injection) * dt
        injected_change = injection.T - self.aquifer_temperature
        heat = self._fluid_heat_capacity(injection) * volume
        states = {}
        for store in STORES:
            store_volume, change = self._moved_store(store, volume, injected_change)
            decay = self._decay(store_volume, injection, dt)
            states[f"{store}_volume"] = store_volume
            states[f"{store}_temperature_change"] = change * decay
        charging = self.mode == "charge"
        states["charged_heat"] = self.charged_heat + (heat * injected_change if charging else 0)
        discharging = self.mode == "discharge"
        recovered = heat * self.warm_temperature_change if discharging else 0
        states["recovered_heat"] = self.recovered_heat + recovered
        return states

    def production_temperature(self):
        """Return the temperature [K] that ``production_out`` has in the running step.

        It uses ``start_states()``: the start-of-step states inside a parent's ``Module.step``,
        otherwise the initial states, like a call of the module would. ``mode`` resolves as in
        a call without a ``mode`` keyword (persisted value, then default). Plants call this
        before the module to evaluate the equipment between production and injection.
        """
        return self._production_temperature(self.start_states())

    def _moved_store(self, store, volume, injected_change):
        """Return a store's volume [m3] and temperature change [K] after this step's flow."""
        store_volume, change = self._volume(store), self._change(store)
        source, target = SOURCE_AND_TARGET.get(self.mode, (None, None))
        if store == target:
            mixed = store_volume + volume
            blended = (store_volume * change + volume * injected_change) / mixed
            return ops.where(volume > 0, mixed, store_volume), ops.where(
                volume > 0, blended, change
            )
        if store == source:
            return ops.maximum(store_volume - volume, 0.0), change
        return store_volume, change

    def _decay(self, store_volume, injection, dt):
        """Return exp(-dt UA / ((rho c)_w V)) [-] of a store; an empty store has no excess."""
        conductance = self._store_conductance(store_volume, injection)
        return ops.where(
            store_volume == 0,
            0.0,
            ops.exp(-dt * conductance / (self._fluid_heat_capacity(injection) * store_volume)),
        )

    def _production_temperature(self, states):
        """Return the temperature [K] of the store produced from in the current mode."""
        source, _ = SOURCE_AND_TARGET.get(self.mode, (None, None))
        if source is None:
            return self.aquifer_temperature
        return self.aquifer_temperature + states[f"{source}_temperature_change"]

    def _store_conductance(self, store_volume, injection):
        """Return the conduction conductance [W/K] of a store of water volume [m3]."""
        fluid = self._fluid_heat_capacity(injection)
        aquifer = ground.aquifer_volumetric_heat_capacity(
            self.porosity, fluid, self.rock_volumetric_heat_capacity
        )
        return ground.cylinder_store_conductance(
            self.ground_conductivity,
            self.ground_conductivity / aquifer,
            store_volume * fluid / aquifer,
            self.aquifer_thickness,
            self.storage_period,
        )

    def _start_states(self):
        """Return the store temperature changes [K] at the start of the running step."""
        return {f"{store}_temperature_change": self._change(store) for store in STORES}

    def _volume(self, store):
        """Return a store's water volume [m3] at the start of the step."""
        return getattr(self, f"{store}_volume")

    def _change(self, store):
        """Return a store's temperature change [K] at the start of the step."""
        return getattr(self, f"{store}_temperature_change")

    @staticmethod
    def _fluid_heat_capacity(stream):
        """Return the volumetric heat capacity (rho c)_w [J/m3/K] of the circuit liquid."""
        fluid = stream.fluid.properties(stream.p, stream.T)
        return fluid.rho_l * fluid.cp_l

    def _volume_flow(self, injection):
        """Return the injected liquid volume flow [m3/s] after checking it against the mode."""
        ops.check(
            injection.m_dot >= 0,
            PhysicsRangeError,
            "{path}: injection_in.m_dot = {m_dot} kg/s; expected >= 0 "
            "(the mode sets the direction)",
            path=self.path,
            m_dot=injection.m_dot,
        )
        if self.mode == "idle":
            ops.check(
                injection.m_dot == 0,
                PhysicsRangeError,
                "{path}: injection_in.m_dot = {m_dot} kg/s in idle mode; expected 0",
                path=self.path,
                m_dot=injection.m_dot,
            )
        return injection.m_dot / injection.fluid.properties(injection.p, injection.T).rho_l


def _enthalpy_flow(stream):
    """Return the sensible enthalpy flow m_dot cp T [W] of a stream, as ``energy_balance``."""
    return stream.heat_capacity_rate() * stream.T
