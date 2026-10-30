"""Building or process cooling demand on a chilled-water circuit, with latent load."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules.module import Module
from gemini.physics import heat_transfer, psychrometrics
from gemini.types import (
    Boundary,
    Fraction,
    HeatAbsorbed,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Stream,
    Temperature,
    TemperatureDifference,
)


class CoolingConsumer(Module):
    """Cooling consumer that warms the chilled-water supply by the sensible and latent loads.

    The circuit's mass flow is imposed by the supply stream, so the return temperature follows
    from the heat taken from the building:

    T_limit = min(maximum_return_temperature, indoor_temperature)
    Q_available = m_dot cp max(0, T_limit - T_supply)
    Q_sensible = min(sensible_cooling_demand, Q_available)
    Q_latent = min(latent_cooling_demand, Q_available - Q_sensible)  if T_supply <= T_dew - margin
    Q_latent = 0                                                     otherwise
    T_return = T_supply + (Q_sensible + Q_latent) / (m_dot cp)

    The dew point ``T_dew`` of the indoor air comes from ``psychrometrics.dew_point`` (Hyland and
    Wexler 1983 saturation pressure, ASHRAE Handbook - Fundamentals 2017, chapter 1). Moisture
    condenses on a coil only when its surface is below the dew point; the coil surface is warmer
    than the water, so dehumidification needs a supply at least ``dew_point_margin`` below the
    dew point (the coil apparatus dew point approach, ASHRAE Handbook - HVAC Systems and
    Equipment 2020, chapter 23, "Air-cooling and dehumidifying coils"). Otherwise the latent
    load is unmet, as with chilled beams or radiant ceilings run above the dew point. The water
    cannot return warmer than the indoor air that heats it, hence the indoor temperature in
    ``T_limit``.

    When the available capacity is short, the sensible load is served first: room thermostats
    control the dry-bulb temperature and humidity drifts. The latent heat (condensation of the
    removed vapour) enters the water like the sensible heat, so ``heat_absorbed`` is their sum;
    the condensate drains on the air side and the water mass flow is unchanged.

    Simplifications: steady state, constant fluid properties (the inlet ``cp``), no pressure
    drop, no coil characteristic beyond the return limit and the dew-point test, and loads
    given as boundaries instead of computed from the air side. The model conserves mass and is
    first-law closed: the sensible enthalpy rise of the stream equals ``heat_absorbed``. Valid
    for chilled water or glycol with nonnegative flow and indoor air from 173.15 K to 473.15 K
    with a relative humidity in (0, 1].
    """

    def __init__(self):
        """Declare the consumer's limits, indoor conditions, loads and absorbed heat."""
        super().__init__()

        # Parameters
        self.maximum_return_temperature = Parameter(Temperature)
        self.dew_point_margin = Parameter(TemperatureDifference, ge=0)

        # Inlets
        self.supply_in = Inlet(Stream, stream="chilled_water")

        # Boundaries
        self.sensible_cooling_demand = Boundary(Power, ge=0)
        self.latent_cooling_demand = Boundary(Power, ge=0)
        self.indoor_temperature = Boundary(Temperature)
        self.indoor_relative_humidity = Boundary(Fraction, gt=0)

        # Outputs
        self.heat_absorbed = Output(HeatAbsorbed)
        self.unmet_sensible = Output(Power)
        self.unmet_latent = Output(Power)
        self.dew_point = Output(Temperature)
        self.return_out_T = Output(Temperature)
        self.is_unmet = Output(bool)

        # Outlets
        self.return_out = Outlet(Stream, stream="chilled_water")

    def forward(self, inlets):
        """Return the supply stream warmed by the absorbed building heat."""

        # Outlets
        supply_in = inlets.supply_in
        sensible, latent = self._met_loads(supply_in)
        absorbed = sensible + latent
        warmed = ops.minimum(
            self._return_limit(),
            supply_in.T
            + heat_transfer.temperature_change(absorbed, supply_in.heat_capacity_rate()),
        )
        return_T = ops.where(absorbed == 0, supply_in.T, warmed)
        return_out = supply_in.with_(T=return_T)

        outlets = dict(return_out=return_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        sensible, latent = self._met_loads(inlets.supply_in)
        self.heat_absorbed = sensible + latent
        self.unmet_sensible = self.sensible_cooling_demand - sensible
        self.unmet_latent = self.latent_cooling_demand - latent
        self.dew_point = psychrometrics.dew_point(
            self.indoor_temperature, self.indoor_relative_humidity
        )
        self.return_out_T = outlets.return_out.T
        self.is_unmet = ops.logical_or(self.unmet_sensible > 0, self.unmet_latent > 0)

    def _met_loads(self, supply_in):
        """Return the met sensible and latent loads [W]."""
        ops.check(
            supply_in.m_dot >= 0,
            PhysicsError,
            "{path}: supply_in.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=supply_in.m_dot,
        )
        available = heat_transfer.setpoint_duty(
            supply_in.heat_capacity_rate(), self._return_limit() - supply_in.T
        )
        dew_point = psychrometrics.dew_point(self.indoor_temperature, self.indoor_relative_humidity)
        dry = supply_in.T > dew_point - self.dew_point_margin
        return heat_transfer.sensible_latent_loads(
            available, self.sensible_cooling_demand, self.latent_cooling_demand, dry
        )

    def _return_limit(self):
        """Return the warmest return temperature [K]: the parameter or the indoor air."""
        return ops.minimum(self.maximum_return_temperature, self.indoor_temperature)
