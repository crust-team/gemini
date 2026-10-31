"""A doublet: production and injection limbs, designed from its depth or set by hand."""

from gemini.modules.environment import Formation
from gemini.modules.plant import Plant
from gemini.modules.pumps import ESP
from gemini.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.modules.wells import InjectionWell, ProductionWell
from gemini.physics import constants, doublet, ground, pumps
from gemini.types import (
    Efficiency,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Permeability,
    Power,
    Pressure,
    Stream,
    Temperature,
    TemperatureGradient,
    VolumeFlow,
)
from gemini.types.cost import scaled_cost

WELL_COUNT = 2
"""The producer and the injector of a doublet."""


class Doublet(Plant):
    """Production and injection limbs, with the children's values derived from a design.

    ``depth`` is the true vertical depth of the reservoir midpoint, ``thickness`` its gross
    thickness and ``well_diameter`` the inner diameter of both vertical wells. ``set_params``
    derives, through ``gemini/physics/doublet.py``:

    - from ``depth``, ``gradient`` and ``surface_temperature``: the reservoir temperature at the
      midpoint, the hydrostatic reservoir pressure from the fluid density, the top depth and the
      soil temperature of the wells, the geotherm at half the depth;
    - with ``permeability``, ``thickness`` and ``well_diameter``: the productivity and injectivity
      indices of radial Darcy flow, with the fluid viscosity, ``drainage_radius``, the wellbore
      radius and the ``skin`` of each reservoir, and the vertical pipe paths of the wells;
    - with ``nominal_flow``, ``pump_efficiency`` and ``nominal_wellhead_pressure``: the pump setting
      depth, the shallowest that keeps that pressure at the intake, and a one-stage ESP of constant
      head that reaches the wellhead pressure at the nominal flow, with that hydraulic efficiency.

    A group of values that is not complete derives nothing, and the old way, setting every child
    value directly, works as it did. A child value in the same call wins over the derived one and
    stays explicit. Setting ``fluid`` gives it to every child and derives again.
    """

    def __init__(self):
        """Declare the limbs, the design values, the ports and the connections."""
        super().__init__()

        # Modules
        self.reservoir = ProductionReservoir()
        self.well = ProductionWell()
        self.esp = ESP()
        self.riser = ProductionWell()
        self.injector = InjectionWell()
        self.sink = InjectionReservoir()
        self.formation = Formation()

        # Parameters
        self.depth = Parameter(Length | None, default=None)
        self.gradient = Parameter(TemperatureGradient | None, default=None)
        self.surface_temperature = Parameter(Temperature | None, default=None)
        self.permeability = Parameter(Permeability | None, default=None)
        self.thickness = Parameter(Length | None, default=None)
        self.well_diameter = Parameter(Length | None, default=None)
        self.drainage_radius = Parameter(Length, default=ground.DOUBLET_WELL_SPACING, gt=0)
        self.nominal_flow = Parameter(VolumeFlow | None, default=None)
        self.pump_efficiency = Parameter(Efficiency | None, default=None)
        self.nominal_wellhead_pressure = Parameter(Pressure | None, default=None)

        # Inlets
        self.return_in = Inlet(Stream)
        self.power_in = Inlet(Power, kind="electricity")

        # Outlets
        self.supply_out = Outlet(Stream)

        # Connections
        self.connect("return_in", "injector.wellhead_in")
        self.connect("power_in", "esp.power_in")
        self.connect("injector.bottom_out", "sink.sandface_in")
        self.connect("reservoir.sandface_out", "well.bottom_in")
        self.connect("well.wellhead_out", "esp.fluid_in")
        self.connect("esp.fluid_out", "riser.bottom_in")
        self.connect("well.loss_out", "formation.heat_in")
        self.connect("riser.loss_out", "formation.heat_in")
        self.connect("injector.loss_out", "formation.heat_in")
        self.connect("riser.wellhead_out", "supply_out")

        # Outputs
        self.brine_cooling = Output.difference("riser.wellhead_out.T", "injector.wellhead_in.T")

    def set_params(self, path, params, valid_from=None):
        """Derive the children's values from the design, unless the same call states them."""
        if path:
            return super().set_params(path, params, valid_from)
        fluid = self.fluid.properties(0, 0)
        derived = doublet.design(
            self._own_values(params, valid_from),
            fluid.rho_l,
            fluid.mu_l,
            {name: self.get_submodule(name).skin for name in doublet.RESERVOIRS},
            self._stated_pressure(params),
        )
        return super().set_params("", self._keep_derived(derived, params) | params, valid_from)

    def _stated_pressure(self, params):
        """Return the reservoir pressure [Pa] stated by hand, in this call or earlier, or None."""
        if "reservoir.pressure" in params:
            return self.get("reservoir.pressure").validate(params["reservoir.pressure"])
        return (
            self.reservoir.pressure if "reservoir.pressure" in self._stated_child_params else None
        )

    def capex(self, assumptions):
        """Return the cost of the design: both wells by the metre and the pump by its power.

        A doublet without a design declares no cost; its children's own costs stand.
        """
        if self.depth is None:
            return None
        wells = scaled_cost(assumptions, "drilling_cost", WELL_COUNT * self.depth)
        if self.nominal_flow is None:
            return wells
        power = pumps.power(
            self.nominal_flow,
            float(constants.ESP_REFERENCE_FREQUENCY),
            self.esp.stage_count,
            self.esp.power_coefficients,
        )
        pump = scaled_cost(assumptions, "pump_cost", power)
        source = f"{wells.source}; {pump.source}"
        return wells.model_copy(update={"capex": wells.capex + pump.capex, "source": source})
