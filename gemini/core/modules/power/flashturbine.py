"""Single-flash condensing steam turbine with Baumann wet-expansion losses."""

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.physics import steam
from gemini.core.types import (
    WATER,
    Efficiency,
    ElectricityGenerated,
    Fraction,
    HeatLoss,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Pressure,
    Ratio,
    Stream,
)
from gemini.errors import PhysicsRangeError


class FlashTurbine(Module):
    """Condensing steam turbine and generator fed with dry saturated steam from a separator.

    The inlet is dry saturated steam (``Fluid`` kind ``steam``, as ``Separator.gas`` emits) at
    the inlet pressure; the inlet temperature is not used because the pressure fixes the
    saturated state. The steam expands to ``condenser_pressure`` with the Baumann rule:
    eta = eta_dry (1 - a (1 - x_out) / 2) for the mean exhaust moisture (see
    ``physics.steam.baumann_expansion``). The generator converts ``gross_power`` (shaft power)
    with ``generator_efficiency``. The condenser condenses the exhaust to saturated liquid at
    the condenser pressure, which leaves through ``outlet`` as water.

    ``heat_loss`` is the condenser duty plus the generator loss, so the module is closed in
    IF97 enthalpies: m h_g(p_in) = electricity_generated + heat_loss + m h_f(p_cond).

    NOTE(refactor): ``energy_balance`` audits sensible enthalpy ``m_dot * cp_l * T`` and
    cannot represent the latent heat of the steam, so its residual is not valid for this phase
    change; the unit tests check closure with the steam enthalpies instead.

    Defaults: ``isentropic_efficiency`` 0.85 is the dry turbine efficiency DiPippo assumes for
    geothermal steam turbines and ``baumann_factor`` 1 is the classical Baumann rule
    (DiPippo, R. (2016), Geothermal Power Plants, 4th ed., section 5.5). Assumptions: no
    non-condensable gases, steam ejector or gland losses; condenser at a fixed pressure.
    Valid for inlet pressures up to 16.529 MPa above a condenser pressure of at least
    611.213 Pa, with a wet exhaust.
    """

    category = "heat_exchange"

    def __init__(self):
        """Declare turbine and generator design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.isentropic_efficiency = Parameter(Efficiency, default=0.85)
        self.baumann_factor = Parameter(Ratio, default=1)
        self.condenser_pressure = Parameter(Pressure, gt=0)
        self.generator_efficiency = Parameter(Efficiency)

        # Inlets
        self.inlet = Inlet(Stream, stream="gas")

        # Outputs
        self.gross_power = Output(Power)
        self.electricity_generated = Output(ElectricityGenerated)
        self.condenser_duty = Output(Power)
        self.heat_loss = Output(HeatLoss)
        self.exhaust_quality = Output(Fraction)

        # Outlets
        self.outlet = Outlet(Stream, stream="gas")

    def forward(self, inlets):
        """Expand the steam and return the condensate at the condenser saturation state."""

        # Outlets
        inlet = inlets.inlet
        ops.require(self._expansion(inlet))
        condenser = steam.saturation_properties(self.condenser_pressure)

        outlet = inlet.with_(T=condenser.temperature, p=self.condenser_pressure, fluid=WATER)

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        expansion = self._expansion(inlet)
        condensate = steam.saturation_properties(self.condenser_pressure).liquid_enthalpy
        self.gross_power = inlet.m_dot * (expansion.inlet_enthalpy - expansion.outlet_enthalpy)
        self.electricity_generated = self.gross_power * self.generator_efficiency
        self.condenser_duty = inlet.m_dot * (expansion.outlet_enthalpy - condensate)
        self.heat_loss = self.condenser_duty + self.gross_power - self.electricity_generated
        self.exhaust_quality = expansion.outlet_quality

    def _expansion(self, inlet):
        """Return the Baumann expansion of the inlet steam to the condenser pressure.

        Raises ``PhysicsRangeError`` outside the model domain; ``forward`` calls it to reject
        such an inlet before it emits the condensate.
        """
        ops.check(
            inlet.m_dot >= 0,
            PhysicsRangeError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        if inlet.fluid.kind != "steam":
            raise PhysicsRangeError(
                f"{self.path}: inlet.fluid.kind = {inlet.fluid.kind!r}; expected 'steam'"
            )
        ops.check(
            inlet.p > self.condenser_pressure,
            PhysicsRangeError,
            "{path}: inlet.p = {p} Pa; expected above the condenser pressure "
            "{condenser_pressure} Pa",
            path=self.path,
            p=inlet.p,
            condenser_pressure=self.condenser_pressure,
        )
        return steam.baumann_expansion(
            inlet.p, self.condenser_pressure, self.isentropic_efficiency, self.baumann_factor
        )
