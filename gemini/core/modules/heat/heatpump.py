"""Electric vapour-compression heat pump or chiller with a Carnot-fraction COP."""

from typing import Literal

from gemini.core.modules.module import Module
from gemini.core.physics import refrigeration
from gemini.core.types import (
    Control,
    Efficiency,
    Fraction,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    Ratio,
    Stream,
    Temperature,
    TemperatureDifference,
)
from gemini.errors import PhysicsRangeError


class HeatPump(Module):
    """Electric vapour-compression heat pump; in cooling mode it is an electric chiller.

    The evaporator cools the ``source_in`` circuit and the condenser heats the ``sink_in``
    circuit, both water or brine. In ``heating`` mode ``temperature_setpoint`` is the sink
    outlet temperature and the useful duty is the condenser duty; in ``cooling`` mode it is the
    chilled (source) outlet temperature and the useful duty is the evaporator duty, so a
    cooling-mode heat pump is an electric chiller. The useful duty is
    ``min(requested, capacity)``; below ``minimum_part_load * capacity`` the machine is off.

    COP = carnot_efficiency * T_sink_out / max(T_sink_out - T_source_out, minimum_temperature_lift)
    when heating and carnot_efficiency * T_source_out / max(...) when cooling, from the outlet
    temperatures of both circuits. Because one outlet temperature depends on the COP, the
    balance Q_sink = Q_source + electricity is solved in closed form (it is linear in the
    unknown outlet temperature). The model is first-law closed.

    Assumptions: constant Carnot fraction over load and temperatures (no part-load or
    compressor-map effects), no pressure loss, no heat loss from the casing, constant liquid
    heat capacity per stream. A machine with either circuit stopped does not run. Validity: a
    lift of about 10 to 80 K between outlet temperatures, the range of the water-to-water
    machines summarised by Arpagaus et al. (2018), "High temperature heat pumps: Market overview,
    state of the art, research status, refrigerants, and application potentials", Energy 152,
    985-1010, who report Carnot fractions of about 0.4 to 0.6 (default 0.5). Outlet temperatures
    are not checked against the freezing point of the fluid.
    """

    def __init__(self):
        """Declare heat pump design data, both circuits and computed performance."""
        super().__init__()

        # Parameters
        self.mode = Parameter(Literal["heating", "cooling"])
        self.capacity = Parameter(Power, gt=0)
        self.carnot_efficiency = Parameter(Efficiency, default=0.5)
        self.minimum_temperature_lift = Parameter(TemperatureDifference, default=10, gt=0)
        self.minimum_part_load = Parameter(Fraction, default=0)

        # Inlets
        self.source_in = Inlet(Stream)
        self.sink_in = Inlet(Stream)

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Outputs
        self.cop = Output(Ratio | None)
        self.useful_duty = Output(Power)
        self.evaporator_duty = Output(Power)
        self.condenser_duty = Output(Power)
        self.electricity = Output(Power)
        self.temperature_lift = Output(TemperatureDifference)
        self.is_capped = Output(bool)
        self.is_running = Output(bool)
        self.source_out_T = Output(Temperature)
        self.sink_out_T = Output(Temperature)

        # Outlets
        self.source_out = Outlet(Stream)
        self.sink_out = Outlet(Stream)

    def forward(self, inlets):
        """Cool the source and heat the sink circuit by the solved duties."""

        # Outlets
        values = self._performance(inlets.source_in, inlets.sink_in)
        source_out = inlets.source_in.with_(T=values["source_out_T"])
        sink_out = inlets.sink_in.with_(T=values["sink_out_T"])

        outlets = dict(source_out=source_out, sink_out=sink_out)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        values = self._performance(inlets.source_in, inlets.sink_in)
        for name, value in values.items():
            setattr(self, name, value)

    def _performance(self, source_in, sink_in):
        """Return every output; the outlet temperatures [K] also define the outlets."""
        source_rate = _rate(self.path, "source_in", source_in)
        sink_rate = _rate(self.path, "sink_in", sink_in)
        heating = self.mode == "heating"
        if heating:
            requested = sink_rate * max(0, self.temperature_setpoint - sink_in.T)
        else:
            requested = source_rate * max(0, source_in.T - self.temperature_setpoint)
        duty = 0.0
        if source_rate and sink_rate:
            duty = refrigeration.part_load_duty(requested, self.capacity, self.minimum_part_load)
        if heating:
            sink_T = sink_in.T + duty / sink_rate if duty else sink_in.T
            source_T = self._source_outlet_T(source_in.T, source_rate, sink_T, duty)
            evaporator, condenser = duty - duty / self._cop(sink_T, source_T), duty
        else:
            source_T = source_in.T - duty / source_rate if duty else source_in.T
            sink_T = self._sink_outlet_T(sink_in.T, sink_rate, source_T, duty)
            evaporator, condenser = duty, duty + duty / self._cop(sink_T, source_T)
        return {
            "cop": self._cop(sink_T, source_T) if duty else None,
            "useful_duty": duty,
            "evaporator_duty": evaporator,
            "condenser_duty": condenser,
            "electricity": condenser - evaporator,
            "temperature_lift": sink_T - source_T,
            "is_capped": bool(duty) and requested > self.capacity,
            "is_running": duty > 0,
            "source_out_T": source_T,
            "sink_out_T": sink_T,
        }

    def _cop(self, sink_T, source_T):
        """Return the Carnot-fraction COP [-] of the mode at the given outlet temperatures [K]."""
        lift = self.minimum_temperature_lift
        if self.mode == "heating":
            cop = refrigeration.carnot_cop_heating(sink_T, source_T, lift)
            return self.carnot_efficiency * cop
        return self.carnot_efficiency * refrigeration.carnot_cop_cooling(sink_T, source_T, lift)

    def _source_outlet_T(self, inlet_T, rate, sink_T, duty):
        """Return the source outlet [K] that balances a heating duty [W] at sink outlet sink_T.

        With COP = eta * T_h / lift, Q_source = Q * (1 - lift / (eta * T_h)) is linear in the
        source outlet temperature x. The floored lift applies when it gives x within the floor;
        otherwise x = (T_in - Q/C * (1 - 1/eta)) / (1 + Q / (C * eta * T_h)).
        """
        if not duty:
            return inlet_T
        eta, lift, load = self.carnot_efficiency, self.minimum_temperature_lift, duty / rate
        floored = inlet_T - load * (1 - lift / (eta * sink_T))
        outlet_T = floored
        if sink_T - floored > lift:
            outlet_T = (inlet_T - load * (1 - 1 / eta)) / (1 + load / (eta * sink_T))
        if self._cop(sink_T, outlet_T) <= 1:
            raise PhysicsRangeError(
                f"{self.path}: source_in.T = {inlet_T} K; expected above "
                f"{(1 - eta) * sink_T} K for a heating COP above 1 at sink outlet {sink_T} K"
            )
        return outlet_T

    def _sink_outlet_T(self, inlet_T, rate, source_T, duty):
        """Return the sink outlet [K] that rejects a cooling duty [W] at source outlet source_T.

        With COP = eta * T_c / lift, Q_sink = Q * (1 + lift / (eta * T_c)) is linear in the sink
        outlet temperature y. The floored lift applies when it gives y within the floor;
        otherwise y = (T_in + Q/C * (1 - 1/eta)) / (1 - Q / (C * eta * T_c)), which needs a sink
        capacity rate C above Q / (eta * T_c).
        """
        if not duty:
            return inlet_T
        eta, lift, load = self.carnot_efficiency, self.minimum_temperature_lift, duty / rate
        floored = inlet_T + load * (1 + lift / (eta * source_T))
        if floored - source_T <= lift:
            return floored
        denominator = 1 - load / (eta * source_T)
        if denominator <= 0:
            raise PhysicsRangeError(
                f"{self.path}: sink_in.m_dot * cp = {rate} W/K; expected above "
                f"{duty / (eta * source_T)} W/K to reject the cooling duty {duty} W"
            )
        return (inlet_T + load * (1 - 1 / eta)) / denominator


def _rate(path, port, stream):
    """Return a stream's heat capacity rate m_dot * cp [W/K]; reject negative flow."""
    if stream.m_dot < 0:
        raise PhysicsRangeError(f"{path}: {port}.m_dot = {stream.m_dot} kg/s; expected >= 0")
    return stream.m_dot * stream.fluid.properties(stream.p, stream.T).cp_l
