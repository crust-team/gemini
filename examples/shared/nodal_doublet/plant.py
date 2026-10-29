"""Doublet produced against a wellhead pressure and injected through a solved pump head."""

from gemini.core.modules import Module
from gemini.core.modules.plants import nodal
from gemini.core.modules.pumps import ESP, InjectionPump
from gemini.core.modules.subsurface import (
    InjectionReservoir,
    InjectionWell,
    ProductionReservoir,
    ProductionWell,
)
from gemini.core.types import Boundary, Inlet, MassFlow, Outlet, Output, Parameter, Pressure, Stream


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

        # Boundaries
        self.wellhead_pressure = Boundary(Pressure)

        # Outputs
        self.electricity = Output.total("electricity")
        self.heat_loss = Output.total("heat_loss")

        # Outlets
        self.supply_out = Outlet(Stream)

    def forward(self, inlets):
        """Inject the return stream and produce the supply stream."""

        # Modules
        self.inject(inlets.return_in)

        # Outlets
        supply_out = self.produce()

        outlets = dict(supply_out=supply_out)
        return outlets

    def produce(self):
        """Solve the production rate for the wellhead pressure and traverse the limb at it."""
        rate = nodal.solve_production_rate(
            self.reservoir,
            self.well,
            self.wellhead_pressure,
            self.production_rates,
            esp=self.esp,
            riser=self.riser,
        )
        source = self.reservoir(production_rate=rate)
        lower = self.well(bottom=source.outlets.sandface)
        lifted = self.esp(suction=lower.outlets.wellhead)
        upper = self.riser(bottom=lifted.outlets.discharge)
        return upper.outlets.wellhead

    def inject(self, stream):
        """Pump ``stream`` to the solved wellhead pressure, or not at all, and inject it."""
        bracket = (stream.p, self.maximum_injection_pressure)
        required = nodal.solve_injection_pressure(self.injector, self.sink, stream, bracket)
        setpoint = stream.p if required is None else required
        pumped = self.injection_pump(suction=stream, pressure_setpoint=setpoint)
        injection = self.injector(wellhead=pumped.outlets.discharge)
        self.sink(sandface=injection.outlets.bottom)
