"""The gas grid as a source, and the in-line mark that a burner may draw from it."""

from gemini.modules.module import Module
from gemini.physics import gas
from gemini.types import Fraction, Inlet, Outlet, Parameter, Stream
from gemini.types.cost import scaled_cost
from gemini.types.fluid import grid_gas


class GasGrid(Module):
    """Gas grid: the fuel source of a burner that has no co-produced gas.

    The ``outlet`` carries no flow: purchased gas enters no stream, and the burner reports it as
    ``fuel_purchased``. The stream marks that the burner may draw grid gas of ``composition``, by
    default the published grid analysis of ``gas.GRID_COMPOSITION``, and leaves at normal
    conditions.
    """

    def __init__(self):
        """Declare the grid gas composition and the outlet."""
        super().__init__()

        # Parameters
        self.composition = Parameter(
            dict[str, Fraction], default=gas.GRID_COMPOSITION, structural=True
        )

        # Outlets
        self.fluid_out = Outlet(Stream, kind="gas")

    def forward(self, inlets):
        """Emit the marked stream without flow."""

        # Outlets
        outlet = Stream(
            m_dot=0.0,
            T=gas.NORMAL_TEMPERATURE,
            p=gas.NORMAL_PRESSURE,
            fluid=grid_gas(self.composition),
        )

        outlets = dict(fluid_out=outlet)
        return outlets


class GasMakeup(Module):
    """In-line mark between a degasser and a burner: the burner may draw grid gas.

    The ``outlet`` is the inlet gas, marked with the grid gas ``composition``, by default the
    published grid analysis of ``gas.GRID_COMPOSITION``. The burner buys what the co-produced gas
    does not cover, so this module shows the grid connection on the flowsheet and moves no gas.
    """

    def __init__(self):
        """Declare the grid gas composition and the in-line ports."""
        super().__init__()

        # Parameters
        self.composition = Parameter(
            dict[str, Fraction], default=gas.GRID_COMPOSITION, structural=True
        )

        # Inlets
        self.fluid_in = Inlet(Stream, kind="gas")

        # Outlets
        self.fluid_out = Outlet(Stream, kind="gas")

    def forward(self, inlets):
        """Pass the gas on with the grid mark."""

        # Outlets
        inlet = inlets.fluid_in
        outlet = inlet.with_(fluid=inlet.fluid.with_grid(self.composition))

        outlets = dict(fluid_out=outlet)
        return outlets

    def capex(self, assumptions):
        """Return the cost of the grid connection, a fixed item."""
        return scaled_cost(assumptions, "makeup_cost")
