"""Ideal-gas compressor for separated non-condensable gas."""

from gemini.core.modules.module import Module
from gemini.core.physics import compression
from gemini.core.types import (
    Control,
    Count,
    Efficiency,
    Electricity,
    HeatLoss,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Pressure,
    Ratio,
    SpecificHeat,
    Stream,
    Temperature,
)
from gemini.errors import PhysicsRangeError


class GasCompressor(Module):
    """Electric compressor raising the gas from a degasser or separator to a pressure setpoint.

    The gas is an ideal gas with the constant ``gas_specific_heat`` ``cp`` and
    ``heat_capacity_ratio`` ``k``; both are required because the non-condensable gas of
    geothermal brines ranges from nearly pure CO2 to methane-rich mixtures. The suction
    ``Stream`` carries the gas mass flow in ``m_dot`` (as ``Degasser.gas`` does); its ``fluid``
    is passed through unchanged and its liquid property model is not used. The overall pressure
    ratio ``r = pressure_setpoint / p_suction`` is split equally over ``stage_count`` adiabatic
    stages with intercoolers that return the gas to the suction temperature
    (``gemini.core.physics.compression``, GPSA Engineering Data Book, 14th ed., Section 13):

    ``T_2 = T_1 + T_1 (r**((k - 1) / (k N)) - 1) / eta_s``,
    ``P_shaft = m_dot N cp (T_2 - T_1)``, ``electricity = P_shaft / motor_efficiency``.

    The gas leaves the last stage at ``T_2`` (no aftercooler). ``heat_loss`` is the
    intercooler duty ``m_dot (N - 1) cp (T_2 - T_1)`` plus the motor losses, so the model is
    first-law closed in gas enthalpy: ``electricity = m_dot cp (T_2 - T_1) + heat_loss``.
    NOTE(refactor): ``energy_balance`` values every stream with its fluid's liquid ``cp_l``, not
    the gas ``cp``, so its sensible audit is not valid for this module; the unit tests check the
    closure in gas enthalpy instead.

    Valid for gases near ideal behaviour (compressibility factor close to one) and stage
    pressure ratios up to about 4, the usual limit set by the discharge temperature. A
    setpoint below the suction pressure (expansion) and reverse flow raise
    ``PhysicsRangeError``; at zero gas flow the compressor draws no power and the discharge
    temperature is the one the gas would have.
    """

    repr_fields = ("stage_count", "isentropic_efficiency", "heat_capacity_ratio")

    def __init__(self):
        """Declare compressor design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.isentropic_efficiency = Parameter(Efficiency, calibratable=True)
        self.heat_capacity_ratio = Parameter(Ratio, gt=1)
        self.gas_specific_heat = Parameter(SpecificHeat)
        self.stage_count = Parameter(Count, default=1)
        self.motor_efficiency = Parameter(Efficiency)

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.pressure_setpoint = Control(Pressure)

        # Outputs
        self.pressure_ratio = Output(Ratio)
        self.shaft_power = Output(Power, soft_sensor=True)
        self.electricity = Output(Electricity)
        self.discharge_T = Output(Temperature, soft_sensor=True)
        self.heat_loss = Output(HeatLoss)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, inlets):
        """Compress the gas to the pressure setpoint and heat it by the last stage."""

        # Outlets
        suction = inlets.suction
        stage_ratio = self._pressure_ratio(suction) ** (1 / self.stage_count)
        discharge_T = compression.stage_outlet_temperature(
            suction.T, stage_ratio, self.heat_capacity_ratio, self.isentropic_efficiency
        )

        discharge = suction.with_(p=self.pressure_setpoint, T=discharge_T)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        suction = inlets.suction
        discharge = outlets.discharge
        self.pressure_ratio = self._pressure_ratio(suction)
        work = compression.specific_compression_work(
            suction.T,
            self.pressure_ratio,
            self.heat_capacity_ratio,
            self.gas_specific_heat,
            self.isentropic_efficiency,
            self.stage_count,
        )
        self.shaft_power = suction.m_dot * work
        self.electricity = self.shaft_power / self.motor_efficiency
        self.discharge_T = discharge.T
        self.heat_loss = self.electricity - self.shaft_power / self.stage_count

    def _pressure_ratio(self, suction):
        """Return the overall pressure ratio [-]; reject reverse flow and expansion."""
        if suction.m_dot < 0:
            raise PhysicsRangeError(
                f"{self.path}: suction.m_dot = {suction.m_dot} kg/s; reverse flow is unsupported"
            )
        if suction.p <= 0 or self.pressure_setpoint < suction.p:
            raise PhysicsRangeError(
                f"{self.path}: pressure_setpoint = {self.pressure_setpoint} Pa, suction.p = "
                f"{suction.p} Pa; expected a positive suction pressure at or below the setpoint"
            )
        return self.pressure_setpoint / suction.p
