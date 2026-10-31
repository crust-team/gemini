"""Doublet produced against a wellhead pressure and injected through a solved pump head."""

from gemini.modules import Module
from gemini.modules.plants import nodal
from gemini.modules.pumps import ESP, InjectionPump
from gemini.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.modules.wells import InjectionWell, ProductionWell
from gemini.physics import energy
from gemini.types import (
    Boundary,
    Inlet,
    MassFlow,
    Outlet,
    Parameter,
    Power,
    Pressure,
    Stream,
)


class NodalDoublet(Module):
    """Production and injection limbs whose rate and pump head come from nodal analysis.

    The handwritten counterpart of the upstream GEMINI simulator's ``ProducerWell`` and
    ``InjectorWell`` components. ``produce()`` solves the production rate at which the
    reservoir, the well below the ESP, the ESP and the riser deliver the ``wellhead_pressure``
    boundary (``nodal.solve_production_rate`` within ``production_rates``), then traverses the
    limb at that rate. ``inject(stream)`` solves the wellhead pressure the injection well and
    the receiving aquifer need for the returned stream (``nodal.solve_injection_pressure``
    between the stream's own pressure and ``maximum_injection_pressure``) and commands the
    injection pump to it. When no pump is needed (the solve returns ``None``) the pump is
    commanded to its suction pressure, so it adds no head and draws no electricity.

    A parent plant connects the two limbs through its surface equipment, as with ``Doublet``;
    ``forward`` connects them directly.
    """

    def __init__(self):
        """Declare the limbs, the solve brackets and the wellhead boundary."""
        super().__init__()

        # Modules
        self.reservoir = ProductionReservoir()
        self.well = ProductionWell()
        self.esp = ESP()
        self.riser = ProductionWell()
        self.injection_pump = InjectionPump()
        self.injector = InjectionWell()
        self.sink = InjectionReservoir()

        # Parameters
        self.production_rates = Parameter(tuple[MassFlow, MassFlow])
        self.maximum_injection_pressure = Parameter(Pressure)

        # Inlets
        self.return_in = Inlet(Stream)
        self.power_in = Inlet(Power, kind="electricity")

        # Boundaries
        self.wellhead_pressure = Boundary(Pressure)

        # Outlets
        self.supply_out = Outlet(Stream)

    def forward(self, inlets):
        """Inject the return stream and produce the supply stream."""

        # Modules
        injection_power = self.inject(inlets.return_in)

        # Outlets
        supply_out, lift_power = self.produce()
        power_in = energy.total_power([injection_power, lift_power])

        outlets = dict(supply_out=supply_out, power_in=power_in)
        return outlets

    def produce(self):
        """Solve the rate for the wellhead pressure; return the stream and the lift power [W]."""
        rate = nodal.solve_production_rate(
            self.reservoir,
            self.well,
            self.wellhead_pressure,
            self.production_rates,
            esp=self.esp,
            riser=self.riser,
        )
        source = self.reservoir(production_rate=rate)
        lower = self.well(bottom_in=source.outlets.sandface_out)
        lifted = self.esp(fluid_in=lower.outlets.wellhead_out)
        upper = self.riser(bottom_in=lifted.outlets.fluid_out)
        return upper.outlets.wellhead_out, lifted.inlets.power_in

    def inject(self, stream):
        """Pump ``stream`` to the solved pressure and inject it; return the pump power [W]."""
        bracket = (stream.p, self.maximum_injection_pressure)
        required = nodal.solve_injection_pressure(self.injector, self.sink, stream, bracket)
        setpoint = stream.p if required is None else required
        pumped = self.injection_pump(fluid_in=stream, pressure_setpoint=setpoint)
        injection = self.injector(wellhead_in=pumped.outlets.fluid_out)
        self.sink(sandface_in=injection.outlets.bottom_out)
        return pumped.inlets.power_in
