"""Low-temperature ATES plant: well pair, well pump, cooling heat exchanger and heat pump."""

from gemini.modules.exchangers import HeatExchanger
from gemini.modules.heating import HeatPump
from gemini.modules.module import Module
from gemini.modules.pumps import CentrifugalPump
from gemini.modules.storage import AquiferStorage
from gemini.physics import energy
from gemini.types import (
    Control,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Power,
    Pressure,
    Stream,
)


class ATESPlant(Module):
    """Seasonal ATES plant cooling a building circuit in summer and heating it in winter.

    Topology of common low-temperature ATES systems with a heat pump (Fleuchaus et al. 2018,
    "Worldwide application of aquifer thermal energy storage - A review", Renewable and
    Sustainable Energy Reviews 94, 861-876; Bloemendal and Hartog 2018, Geothermics 71,
    306-319), selected by the storage's ``mode`` control:

    - ``"charge"`` (cooling season, free cooling): groundwater from the cold well is pumped
      through the cold side of the ``heat_exchanger``, which cools the building circuit
      (``return_in`` on its hot side, ``supply_out`` its hot outlet), and is injected warmed
      into the warm well. The heat pump is not called.
    - ``"discharge"`` (heating season): groundwater from the warm well is pumped through the
      evaporator (``source_in``) of the ``heat_pump`` and injected cooled into the cold well;
      the condenser heats the building circuit to the heat pump's ``temperature_setpoint``.
      The heat exchanger is not called; the separating exchanger of the winter source circuit
      is lumped into the evaporator.
    - ``"idle"``: the charge topology with ``groundwater_flow`` zero (the storage requires it);
      the building circuit passes the exchanger unchanged except for its pressure drop.

    The groundwater circuit is a loop through the well pair. ``AquiferStorage`` produces at the
    start-of-step temperature of its source store, independent of the injected water, so the
    plant reads ``storage.production_temperature()`` first, builds the produced stream
    (``groundwater_flow`` at ``groundwater_pressure`` with the storage's ``fluid``), passes it
    through ``pump`` and the exchanger or heat pump, and calls the storage once with the result.
    The storage passes pressure through and the well hydraulics are not modelled, so the plant
    injects at ``groundwater_pressure`` again: the pump head minus the exchanger drop is what the
    unmodelled wells and aquifer consume, and the storage's ``production_out`` equals the stream
    fed to the pump. The groundwater flow is a command (``groundwater_flow``), as in ATES
    systems whose well-pump flow follows the building load.

    Every child is first-law closed in its own terms and the storage reports its stored heat
    as ``heat_accumulation``, so ``energy_balance`` closes except for the pump's
    ``hydraulic_power`` (flow work outside the sensible-enthalpy audit). The plant is stateful
    through its storage; ``Module.step`` steps it.
    """

    def __init__(self):
        """Declare the ATES children, the groundwater circuit and the plant totals."""
        super().__init__()

        # Modules
        self.storage = AquiferStorage()
        self.pump = CentrifugalPump()
        self.heat_exchanger = HeatExchanger()
        self.heat_pump = HeatPump()

        # Parameters
        self.groundwater_pressure = Parameter(Pressure, gt=0)

        # Inlets
        self.return_in = Inlet(Stream)
        self.power_in = Inlet(Power, kind="electricity")

        # Controls
        self.groundwater_flow = Control(MassFlow, ge=0)

        # Outputs
        self.heat_accumulation = Output.of(self.storage.heat_accumulation)
        self.stored_energy = Output.of(self.storage.stored_energy)
        self.production_out_T = Output.of(self.storage.production_out.field("T"))
        self.recovery_efficiency = Output.of(self.storage.recovery_efficiency)

        # Outlets
        self.supply_out = Outlet(Stream)
        self.loss_out = Outlet(Power, kind="heat")

    def forward(self, inlets):
        """Produce, condition and reinject the groundwater; serve the building circuit."""

        # Modules
        production = Stream(
            m_dot=self.groundwater_flow,
            T=self.storage.production_temperature(),
            p=self.groundwater_pressure,
            fluid=self.storage.fluid,
        )
        pumped = self.pump(fluid_in=production)
        groundwater = pumped.outlets.fluid_out
        power, losses = [pumped.inlets.power_in], [pumped.outlets.loss_out]
        if self.storage.mode == "discharge":
            lifted = self.heat_pump(source_in=groundwater, sink_in=inlets.return_in)
            injected, building = lifted.outlets.source_out, lifted.outlets.sink_out
            power.append(lifted.inlets.power_in)
        else:
            cooled = self.heat_exchanger(hot_in=inlets.return_in, cold_in=groundwater)
            injected, building = cooled.outlets.cold_out, cooled.outlets.hot_out
        stored = self.storage(injection_in=injected.with_(p=self.groundwater_pressure))
        losses.append(stored.outlets.loss_out)

        # Outlets
        supply_out = building

        power_in = energy.total_power(power)

        loss_out = energy.total_power(losses)

        outlets = dict(supply_out=supply_out, loss_out=loss_out, power_in=power_in)
        return outlets
