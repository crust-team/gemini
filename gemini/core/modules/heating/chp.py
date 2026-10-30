"""Gas-engine combined heat and power unit heating a water circuit."""

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.types import (
    Control,
    Efficiency,
    ElectricityGenerated,
    Fraction,
    Fuel,
    HeatLoss,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Stream,
    Temperature,
)
from gemini.errors import ConfigurationError, PhysicsRangeError


class CHP(Module):
    """Gas-engine combined heat and power unit heating a water circuit.

    ``load_fraction`` L is the electric output as a share of ``electric_capacity``; L = 0 means
    the engine is off. Fuel (lower heating value) follows the Willans line
    F = F_full * (f0 + (1 - f0) * L) for L > 0, with F_full = electric_capacity /
    electric_efficiency and f0 = ``no_load_fuel_fraction`` (Willans-line method in Heywood
    1988, Internal Combustion Engine Fundamentals: fuel flow at constant speed is close to
    linear in brake load). The default f0 = 0 keeps both efficiencies constant over load; a
    typical lean-burn gas engine has its electric efficiency fall by a few points at half load,
    which an f0 of 0.05 to 0.15 reproduces.

    Recoverable engine heat (jacket water, oil and exhaust heat exchanger) is
    thermal_efficiency * F; the circuit takes it up to ``maximum_outlet_temperature`` and a dump
    cooler rejects the rest (``dumped_heat``), so with no water flow all engine heat is dumped.
    heat_loss = F - electricity_generated - heat_recovered (exhaust, radiation and dumped heat),
    so the model is first-law closed.

    Assumptions: steady operation at a constant thermal efficiency on the fuel basis, no
    minimum stable load or start-up losses, no pressure loss, constant liquid heat capacity.
    Validity: L in (0, 1] at rated speed; efficiencies at full load with
    electric_efficiency + thermal_efficiency <= 1 (typical gas engines: 0.35 to 0.44 electric,
    0.40 to 0.50 thermal, from manufacturer data).
    """

    category = "boiler"

    def __init__(self):
        """Declare engine design data, the heated water circuit and energy flows."""
        super().__init__()

        # Parameters
        self.electric_capacity = Parameter(Power, gt=0)
        self.electric_efficiency = Parameter(Efficiency)
        self.thermal_efficiency = Parameter(Efficiency)
        self.no_load_fuel_fraction = Parameter(Fraction, default=0, lt=1)
        self.maximum_outlet_temperature = Parameter(Temperature)

        # Inlets
        self.inlet = Inlet(Stream, stream="hot_water")

        # Controls
        self.load_fraction = Control(Fraction)

        # Outputs
        self.fuel = Output(Fuel)
        self.electricity_generated = Output(ElectricityGenerated)
        self.heat_recovered = Output(Power)
        self.dumped_heat = Output(Power)
        self.heat_loss = Output(HeatLoss)
        self.outlet_T = Output(Temperature)

        # Outlets
        self.outlet = Outlet(Stream, stream="hot_water")

    def forward(self, inlets):
        """Heat the water circuit by the recovered engine heat."""

        # Outlets
        inlet = inlets.inlet
        values = self._performance(inlet)
        outlet = inlet.with_(T=values["outlet_T"])

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        for name, value in self._performance(inlets.inlet).items():
            setattr(self, name, value)

    def _performance(self, inlet):
        """Return fuel, electricity, heat flows [W] and the outlet temperature [K]."""
        ops.check(
            self.electric_efficiency + self.thermal_efficiency <= 1,
            ConfigurationError,
            "{path}: electric_efficiency + thermal_efficiency = {total}; expected <= 1",
            path=self.path,
            total=self.electric_efficiency + self.thermal_efficiency,
        )
        ops.check(
            inlet.m_dot >= 0,
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        load = self.load_fraction
        share = self.no_load_fuel_fraction + (1 - self.no_load_fuel_fraction) * load
        fuel = ops.where(load != 0, share * self.electric_capacity / self.electric_efficiency, 0.0)
        engine_heat = self.thermal_efficiency * fuel
        rate = inlet.heat_capacity_rate()
        recovered = ops.minimum(
            engine_heat, rate * ops.maximum(0, self.maximum_outlet_temperature - inlet.T)
        )
        generated = load * self.electric_capacity
        return {
            "fuel": fuel,
            "electricity_generated": generated,
            "heat_recovered": recovered,
            "dumped_heat": engine_heat - recovered,
            "heat_loss": fuel - generated - recovered,
            "outlet_T": ops.where(recovered != 0, inlet.T + recovered / rate, inlet.T),
        }
