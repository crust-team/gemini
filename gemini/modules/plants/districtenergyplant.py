"""A district heating network and a district cooling network on an aquifer store."""

from gemini.modules.environment import Atmosphere
from gemini.modules.grids import ElectricityGrid
from gemini.modules.module import Module
from gemini.modules.plants._utils import templating
from gemini.modules.plants.atesplant import ATESPlant
from gemini.types import Inlet, Outlet, Output, Stream


class DistrictEnergyPlant(Module):
    """Heating network on a geothermal supply and a cooling network on an ATES plant.

    A geothermal supply on ``hot_in`` feeds a heating network with two building substations. In
    parallel an aquifer thermal energy storage plant in its charge mode chills the water of a
    cooling network that serves one building, and the warmed groundwater is stored in the warm
    well. The return of the cooling network leaves on ``cold_out``; the caller feeds it back to
    ``cold_in`` at the next step.
    """

    def __init__(self):
        """Build both networks and the ATES plant."""
        super().__init__()

        # Modules
        self.heating = templating.from_template("district_network", {"consumers": 2})
        self.ates = ATESPlant()
        self.cooling = templating.from_template(
            "district_network", {"consumers": 1, "service": "cooling"}
        )

        self.electricity_grid = ElectricityGrid()
        self.air = Atmosphere()

        # Inlets
        self.hot_in = Inlet(Stream)
        self.cold_in = Inlet(Stream)
        self.air_in = Inlet(Stream, kind="air")

        # Outputs
        self.stored_energy = Output.of(self.ates.stored_energy)

        # Outlets
        self.hot_out = Outlet(Stream)
        self.cold_out = Outlet(Stream)

    def forward(self, inlets):
        """Serve the heating network, chill the cooling water and serve the cooling network."""

        # Modules
        heated = self.heating(supply_in=inlets.hot_in, air_in=inlets.air_in)
        chilled = self.ates(return_in=inlets.cold_in)
        cooled = self.cooling(supply_in=chilled.outlets.supply_out, air_in=inlets.air_in)
        self.electricity_grid(
            power_in=[],
            power_out=[
                heated.inlets.power_in,
                chilled.inlets.power_in,
                cooled.inlets.power_in,
            ],
        )
        self.air(
            air_in=[],
            gas_in=[],
            heat_in=[
                heated.outlets.loss_out,
                chilled.outlets.loss_out,
                cooled.outlets.loss_out,
            ],
        )

        # Outlets
        hot_out = heated.outlets.return_out
        cold_out = cooled.outlets.return_out

        outlets = dict(hot_out=hot_out, cold_out=cold_out)
        return outlets
