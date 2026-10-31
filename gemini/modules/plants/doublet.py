"""The doublet, a shipped spec plant that can also be designed from its depth."""

from gemini.modules._utils.serialization import module_spec
from gemini.modules.module import Module
from gemini.modules.plant import Plant
from gemini.modules.plants import library, writer
from gemini.physics import constants, geometry, ground, hydraulics, pumps
from gemini.types import (
    Efficiency,
    Length,
    Parameter,
    Permeability,
    Pressure,
    Temperature,
    TemperatureGradient,
    VolumeFlow,
)
from gemini.types.cost import scaled_cost

REQUIRED = ("depth", "gradient", "surface_temperature")
RESERVOIR = ("permeability", "thickness", "well_diameter")
PUMP = ("nominal_flow", "pump_efficiency", "nominal_wellhead_pressure")
RESERVOIRS = ("reservoir", "sink")
WELLS = ("well", "riser", "injector")
WELL_COUNT = 2
"""The producer and the injector of a doublet."""


class Doublet(Plant):
    """The shipped doublet, wired by its spec, with its children's values derived from a design.

    ``depth`` is the true vertical depth of the reservoir midpoint, ``thickness`` its gross
    thickness and ``well_diameter`` the inner diameter of both vertical wells. ``set_params``
    derives, through ``gemini/physics/``:

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
        """Add the modules and wiring of the shipped spec and declare the design values."""
        super().__init__("Doublet")
        library.fill(self, "Doublet")

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

        self._baselines[""] = writer.baseline_of(self)
        self._stated[""] = {}

    @property
    def fluid(self):
        """Return the fluid of the doublet, which all its children carry."""
        return Module.fluid.fget(self)

    @fluid.setter
    def fluid(self, value):
        """Set the fluid of the doublet and of every child and derive again."""
        Module.fluid.fset(self, value)
        for child in self.modules():
            if child is not self:
                child.fluid = value
        self.set_params("", {})

    def set_params(self, path, params, valid_from=None):
        """Derive the children's values from the design, unless the same call states them."""
        if path:
            return super().set_params(path, params, valid_from)
        derived = self._derived(self._own_values(params, valid_from), params)
        self._stated[""] |= params
        kept = self._keep_derived(derived, params)
        return super().set_params("", kept | params, valid_from)

    def to_spec(self):
        """Return the plant file: a design as flat values, a plain doublet as the shipped wiring."""
        params = writer.params_spec(self, "", self)
        if not set(params) & set(self._parameters):
            return super().to_spec()
        return module_spec(self) | {"params": params}

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

    def _derived(self, values, params):
        """Return the child values the design ``values`` give, with ``params`` read for the pump."""
        if any(values[name] is None for name in REQUIRED):
            return {}
        fluid = self.fluid.properties(0, 0)
        derived = _column(values, fluid.rho_l)
        if all(values[name] is not None for name in RESERVOIR):
            derived |= self._flow_paths(values, fluid.mu_l)
            if all(values[name] is not None for name in PUMP):
                derived |= self._pump(values, fluid, self._pressure(params, derived), derived)
        return derived

    def _pressure(self, params, derived):
        """Return the reservoir pressure [Pa]: of this call, stated earlier, or derived."""
        if "reservoir.pressure" in params:
            return self.get_parameter("reservoir.pressure").validate(params["reservoir.pressure"])
        if "reservoir.pressure" in self._stated_child_params:
            return self.reservoir.pressure
        return derived["reservoir.pressure"]

    def _flow_paths(self, values, viscosity):
        """Return the values that follow from the permeability, thickness and well diameter."""
        path = geometry.vertical_path(
            values["depth"], values["well_diameter"], hydraulics.COMMERCIAL_STEEL_ROUGHNESS
        ).model_dump()
        radius = values["well_diameter"] / 2
        derived = {f"{well}.pipe_path": path for well in WELLS}
        for name in RESERVOIRS:
            derived[f"{name}.permeability"] = values["permeability"]
            derived[f"{name}.aquifer_thickness"] = values["thickness"]
            derived[f"{name}.top_depth"] = values["depth"] - values["thickness"] / 2
            derived[f"{name}.drainage_radius"] = values["drainage_radius"]
            derived[f"{name}.wellbore_radius"] = radius
        index = {
            name: hydraulics.radial_index(
                viscosity,
                values["permeability"],
                values["thickness"],
                values["drainage_radius"],
                radius,
                self.get_module(name).skin,
            )
            for name in RESERVOIRS
        }
        derived["reservoir.productivity_index"] = index["reservoir"]
        derived["sink.injectivity_index"] = index["sink"]
        return derived

    def _pump(self, values, fluid, pressure, derived):
        """Return the pump setting depth and the curves of a pump sized at the nominal flow."""
        flow, wellhead = values["nominal_flow"], values["nominal_wellhead_pressure"]
        drawdown = hydraulics.productivity_pressure(
            0.0, -flow, derived["reservoir.productivity_index"]
        )
        setting = hydraulics.pump_setting_depth(
            values["depth"], pressure, drawdown, wellhead, fluid.rho_l
        )
        head = hydraulics.design_pump_head(
            wellhead,
            pressure,
            drawdown,
            fluid.rho_l,
            fluid.mu_l,
            values["depth"],
            values["well_diameter"],
            hydraulics.COMMERCIAL_STEEL_ROUGHNESS,
            flow,
        )
        head_curve, power_curve = pumps.constant_head_curves(head, values["pump_efficiency"])
        return {
            "esp.stage_count": 1,
            "esp.head_coefficients": head_curve,
            "esp.power_coefficients": power_curve,
            "esp.setting_depth": setting,
            "well.esp_depth": setting,
            "well.segment": "below_esp",
            "riser.esp_depth": setting,
            "riser.segment": "above_esp",
        }


def _column(values, density):
    """Return the values that follow from the depth, the geotherm and the fluid density."""
    depth, gradient, surface = values["depth"], values["gradient"], values["surface_temperature"]
    temperature = ground.geotherm_temperature(surface, gradient, depth)
    mean = ground.geotherm_temperature(surface, gradient, depth / 2)
    derived = {f"{well}.soil_temperature": mean for well in WELLS}
    derived["formation.geothermal_gradient"] = gradient
    derived["formation.surface_temperature"] = surface
    for name in RESERVOIRS:
        derived[f"{name}.temperature"] = temperature
        derived[f"{name}.pressure"] = hydraulics.hydrostatic_pressure(density, depth)
    return derived
