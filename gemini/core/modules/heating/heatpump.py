"""Electric vapour-compression heat pump or chiller with a Carnot- or Lorenz-fraction COP."""

from functools import partial
from typing import Literal

from gemini import ops
from gemini.core.modules.module import Module
from gemini.core.physics import refrigeration
from gemini.core.types import (
    Control,
    Efficiency,
    Electricity,
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
from gemini.errors import ConfigurationError, PhysicsRangeError


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

    With ``cop_model="lorenz"`` (heating only) the COP is lorenz_efficiency * T_h /
    max(T_h - T_s, minimum_temperature_lift), with T_h and T_s the log-mean temperatures of the
    sink and source glides (``refrigeration.lorenz_cop_heating``). The source outlet then enters
    the COP through a logarithm, so the balance is solved by ``brentq`` instead of in closed
    form. A cooling-mode Lorenz machine raises ``ConfigurationError``: the upstream GEMINI model
    it is ported from defines the Lorenz COP for heating only.

    Assumptions: constant Carnot fraction over load and temperatures (no part-load or
    compressor-map effects), no pressure loss, no heat loss from the casing, constant liquid
    heat capacity per stream. A machine with either circuit stopped does not run. Validity: a
    lift of about 10 to 80 K between outlet temperatures, the range of the water-to-water
    machines summarised by Arpagaus et al. (2018), "High temperature heat pumps: Market overview,
    state of the art, research status, refrigerants, and application potentials", Energy 152,
    985-1010, who report Carnot fractions of about 0.4 to 0.6 (default 0.5). Outlet temperatures
    are not checked against the freezing point of the fluid unless
    ``minimum_source_outlet_temperature`` is set: it caps a heating duty so the source leaves no
    colder than the minimum (upstream GEMINI ``Ts_in_minimum``) and raises a cooling setpoint
    below it to the minimum.

    Every branch of the operating point is evaluated and selected with ``where``; a stopped
    circuit has a zero capacity rate, whose temperature change ``_load`` takes as zero. The two
    ``ops.brentq`` solves (the Lorenz source outlet and the source-limited duty) are module-level
    functions of their ``args``; a solve that fails gives NaN and raises ``PhysicsRangeError``
    where its row is selected.
    """

    category = "heat_pump"

    def __init__(self):
        """Declare heat pump design data, both circuits and computed performance."""
        super().__init__()

        # Parameters
        self.mode = Parameter(Literal["heating", "cooling"])
        self.capacity = Parameter(Power, gt=0)
        self.cop_model = Parameter(Literal["carnot", "lorenz"], default="carnot")
        self.carnot_efficiency = Parameter(Efficiency, default=0.5)
        self.lorenz_efficiency = Parameter(Efficiency, default=0.5)
        self.minimum_temperature_lift = Parameter(TemperatureDifference, default=10, gt=0)
        self.minimum_part_load = Parameter(Fraction, default=0)
        self.minimum_source_outlet_temperature = Parameter(Temperature | None, default=None)

        # Inlets
        self.source_in = Inlet(Stream)
        self.sink_in = Inlet(Stream, stream="hot_water")

        # Controls
        self.temperature_setpoint = Control(Temperature)

        # Outputs
        self.cop = Output(Ratio | None)
        self.useful_duty = Output(Power)
        self.evaporator_duty = Output(Power)
        self.condenser_duty = Output(Power)
        self.electricity = Output(Electricity)
        self.temperature_lift = Output(TemperatureDifference)
        self.is_capped = Output(bool)
        self.is_running = Output(bool)
        self.source_out_T = Output(Temperature)
        self.sink_out_T = Output(Temperature)

        # Outlets
        self.source_out = Outlet(Stream)
        self.sink_out = Outlet(Stream, stream="hot_water")

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
        if self.cop_model == "lorenz" and not heating:
            raise ConfigurationError(
                f"{self.path}: cop_model = 'lorenz' with mode = 'cooling'; expected "
                "mode = 'heating' (the Lorenz COP is defined for heating only)"
            )
        operate = self._heating if heating else self._cooling
        duty, is_capped, source_T, sink_T = operate(source_in, sink_in, source_rate, sink_rate)
        running = duty != 0
        cop = self._cop(source_in, sink_in, source_T, sink_T)
        evaporator, condenser = duty, duty
        if heating:
            evaporator = ops.where(running, duty - duty / cop, duty)
        if not heating:
            condenser = ops.where(running, duty + duty / cop, duty)
        return {
            "cop": ops.where(running, cop, None),
            "useful_duty": duty,
            "evaporator_duty": evaporator,
            "condenser_duty": condenser,
            "electricity": condenser - evaporator,
            "temperature_lift": sink_T - source_T,
            "is_capped": is_capped,
            "is_running": duty > 0,
            "source_out_T": source_T,
            "sink_out_T": sink_T,
        }

    def _heating(self, source_in, sink_in, source_rate, sink_rate):
        """Return the heating duty [W], the capped flag and the source and sink outlets [K].

        The sink is heated towards the setpoint. When the source outlet would fall below
        ``minimum_source_outlet_temperature``, the duty is reduced until the source leaves at
        that minimum (``_duty_at_source_limit``), the sink outlet drops with it and the machine
        reports ``is_capped``.
        """
        requested = sink_rate * ops.maximum(0, self.temperature_setpoint - sink_in.T)
        duty = self._duty(requested, source_rate, sink_rate)
        sink_T = sink_in.T + _load(duty, sink_rate)
        source_T = self._source_outlet_T(source_in, sink_in, source_rate, sink_T, duty)
        capped = requested > self.capacity
        limit = self.minimum_source_outlet_temperature
        if limit is not None:
            below = ops.logical_not(source_T >= limit)
            limited = self._duty_at_source_limit(
                source_in,
                sink_in,
                source_rate,
                sink_rate,
                duty,
                ops.logical_and(below, duty != 0),
            )
            limited_duty = self._duty(ops.where(below, limited, duty), source_rate, sink_rate)
            duty = ops.where(below, limited_duty, duty)
            capped = ops.where(below, True, capped)
            source_T = ops.where(below, limit, source_T)
            sink_T = ops.where(below, sink_in.T + _load(duty, sink_rate), sink_T)
        stopped = duty == 0
        return (
            ops.where(stopped, 0.0, duty),
            ops.where(stopped, False, capped),
            ops.where(stopped, source_in.T, source_T),
            ops.where(stopped, sink_in.T, sink_T),
        )

    def _cooling(self, source_in, sink_in, source_rate, sink_rate):
        """Return the cooling duty [W], the capped flag and the source and sink outlets [K].

        The source is cooled towards the setpoint, raised to
        ``minimum_source_outlet_temperature`` when that is warmer; a raised setpoint reports
        ``is_capped``.
        """
        limit = self.minimum_source_outlet_temperature
        setpoint = self.temperature_setpoint
        is_limited = False
        if limit is not None:
            is_limited = setpoint < limit
            setpoint = ops.where(is_limited, limit, setpoint)
        requested = source_rate * ops.maximum(0, source_in.T - setpoint)
        duty = self._duty(requested, source_rate, sink_rate)
        source_T = source_in.T - _load(duty, source_rate)
        sink_T = self._sink_outlet_T(sink_in.T, sink_rate, source_T, duty)
        stopped = duty == 0
        capped = ops.logical_or(requested > self.capacity, is_limited)
        return (
            ops.where(stopped, 0.0, duty),
            ops.where(stopped, False, capped),
            ops.where(stopped, source_in.T, source_T),
            ops.where(stopped, sink_in.T, sink_T),
        )

    def _duty(self, requested, source_rate, sink_rate):
        """Return the delivered useful duty [W]: zero with a stopped circuit, else part load."""
        stopped = ops.logical_or(source_rate == 0, sink_rate == 0)
        duty = refrigeration.part_load_duty(
            requested, self.capacity, ops.where(stopped, 0.0, self.minimum_part_load)
        )
        return ops.where(stopped, 0.0, duty)

    def _duty_at_source_limit(self, source_in, sink_in, source_rate, sink_rate, duty, selected):
        """Return the heating duty [W] whose evaporator cools the source exactly to its minimum.

        The evaporator may take at most C_source (T_in - T_min). Its demand Q (1 - 1 / COP),
        with the sink outlet T_sink_in + Q / C_sink and the source outlet T_min in the COP,
        rises from zero at Q = 0 to more than the available heat at the requested duty, whose
        unconstrained source outlet is colder than T_min; ``brentq`` finds the duty between.
        A source inlet at or below the minimum leaves no duty. The solve is checked only where
        ``selected``: the other rows of the batch may have no root.
        """
        limit = self.minimum_source_outlet_temperature
        available = source_rate * (source_in.T - limit)
        root = ops.brentq(
            partial(_shortfall, self._cop_function()),
            0.0,
            duty,
            args=(
                sink_in.T,
                sink_rate,
                source_in.T,
                limit,
                available,
                self._efficiency(),
                self.minimum_temperature_lift,
            ),
        )
        ops.check(
            ops.logical_or(ops.logical_not(selected), ops.logical_or(available <= 0, root == root)),
            PhysicsRangeError,
            "{path}: no heating duty between 0 W and {duty} W cools the source to "
            "{limit} K; expected a source below the minimum at the requested duty",
            path=self.path,
            duty=duty,
            limit=limit,
        )
        return ops.where(available <= 0, 0.0, root)

    def _efficiency(self):
        """Return the Carnot or Lorenz fraction of the COP model [-]."""
        if self.cop_model == "lorenz":
            return self.lorenz_efficiency
        return self.carnot_efficiency

    def _cop_function(self):
        """Return the COP function of the mode and COP model, which all take the same arguments."""
        if self.cop_model == "lorenz":
            return _lorenz_cop
        if self.mode == "heating":
            return _carnot_heating_cop
        return _carnot_cooling_cop

    def _cop(self, source_in, sink_in, source_T, sink_T):
        """Return the COP [-] of the mode and COP model at the given outlet temperatures [K]."""
        return self._cop_function()(
            self._efficiency(),
            self.minimum_temperature_lift,
            sink_in.T,
            sink_T,
            source_in.T,
            source_T,
        )

    def _source_outlet_T(self, source_in, sink_in, rate, sink_T, duty):
        """Return the source outlet [K] that balances a heating duty [W] at sink outlet sink_T.

        With COP = eta * T_h / lift, Q_source = Q * (1 - lift / (eta * T_h)) is linear in the
        source outlet temperature x. The floored lift applies when it gives x within the floor;
        otherwise x = (T_in - Q/C * (1 - 1/eta)) / (1 + Q / (C * eta * T_h)). The Lorenz COP is
        solved numerically by ``_lorenz_source_outlet_T``.
        """
        if self.cop_model == "lorenz":
            return self._lorenz_source_outlet_T(source_in, sink_in, rate, sink_T, duty)
        inlet_T = source_in.T
        eta, lift = self.carnot_efficiency, self.minimum_temperature_lift
        load = _load(duty, rate)
        floored = inlet_T - load * (1 - lift / (eta * sink_T))
        unfloored = (inlet_T - load * (1 - 1 / eta)) / (1 + load / (eta * sink_T))
        outlet_T = ops.where(sink_T - floored > lift, unfloored, floored)
        ops.check(
            ops.where(duty == 0, True, self._cop(source_in, sink_in, outlet_T, sink_T) > 1),
            PhysicsRangeError,
            "{path}: source_in.T = {inlet_T} K; expected above {minimum} K for a heating COP "
            "above 1 at sink outlet {sink_T} K",
            path=self.path,
            inlet_T=inlet_T,
            minimum=(1 - eta) * sink_T,
            sink_T=sink_T,
        )
        return outlet_T

    def _lorenz_source_outlet_T(self, source_in, sink_in, rate, sink_T, duty):
        """Return the source outlet [K] that balances a heating duty [W] with the Lorenz COP.

        The evaporator balance C (T_in - x) = Q (1 - 1 / COP(x)) has its root between
        x = T_in - Q / C, where the left side alone covers the duty, and x = T_in, where it is
        zero; ``brentq`` finds it to within 2e-12 K. A COP of 1 or less already at x = T_in
        means no source outlet can supply the evaporator duty.
        """
        arguments = (
            rate,
            source_in.T,
            sink_in.T,
            sink_T,
            duty,
            self.lorenz_efficiency,
            self.minimum_temperature_lift,
        )
        lower = source_in.T - _load(duty, rate)
        at_inlet = _lorenz_surplus(source_in.T, *arguments)
        ops.check(
            ops.where(duty == 0, True, ops.logical_and(lower > 0, at_inlet < 0)),
            PhysicsRangeError,
            "{path}: source_in.T = {inlet_T} K, source_in.m_dot * cp = {rate} W/K; expected a "
            "source that supplies the duty {duty} W with a heating COP above 1 at sink outlet "
            "{sink_T} K",
            path=self.path,
            inlet_T=source_in.T,
            rate=rate,
            duty=duty,
            sink_T=sink_T,
        )
        root = ops.brentq(
            _lorenz_surplus,
            ops.where(lower > 0, lower, source_in.T),
            source_in.T,
            args=arguments,
        )
        self._check_lorenz_root(root, lower, source_in.T, duty, sink_T)
        return root

    def _check_lorenz_root(self, root, lower, inlet_T, duty, sink_T):
        """Reject a failed evaporator solve on the rows that have a duty."""
        ops.check(
            ops.logical_or(duty == 0, root == root),
            PhysicsRangeError,
            "{path}: no source outlet between {lower} K and {inlet_T} K balances the "
            "evaporator duty {duty} W at sink outlet {sink_T} K",
            path=self.path,
            lower=lower,
            inlet_T=inlet_T,
            duty=duty,
            sink_T=sink_T,
        )

    def _sink_outlet_T(self, inlet_T, rate, source_T, duty):
        """Return the sink outlet [K] that rejects a cooling duty [W] at source outlet source_T.

        With COP = eta * T_c / lift, Q_sink = Q * (1 + lift / (eta * T_c)) is linear in the sink
        outlet temperature y. The floored lift applies when it gives y within the floor;
        otherwise y = (T_in + Q/C * (1 - 1/eta)) / (1 - Q / (C * eta * T_c)), which needs a sink
        capacity rate C above Q / (eta * T_c).
        """
        eta, lift = self.carnot_efficiency, self.minimum_temperature_lift
        load = _load(duty, rate)
        floored = inlet_T + load * (1 + lift / (eta * source_T))
        within_floor = floored - source_T <= lift
        denominator = 1 - load / (eta * source_T)
        ops.check(
            ops.logical_or(ops.logical_or(duty == 0, within_floor), denominator > 0),
            PhysicsRangeError,
            "{path}: sink_in.m_dot * cp = {rate} W/K; expected above {minimum} W/K to reject "
            "the cooling duty {duty} W",
            path=self.path,
            rate=rate,
            minimum=duty / (eta * source_T),
            duty=duty,
        )
        unfloored = (inlet_T + load * (1 - 1 / eta)) / denominator
        return ops.where(within_floor, floored, unfloored)


def _rate(path, port, stream):
    """Return a stream's heat capacity rate m_dot * cp [W/K]; reject negative flow."""
    ops.check(
        stream.m_dot >= 0,
        PhysicsRangeError,
        "{path}: {port}.m_dot = {m_dot} kg/s; expected >= 0",
        path=path,
        port=port,
        m_dot=stream.m_dot,
    )
    return stream.heat_capacity_rate()


def _load(duty, rate):
    """Return the temperature change duty / rate [K] of a circuit, zero for a stopped one.

    A stopped circuit carries no duty, so its zero rate has no change to divide.
    """
    return ops.where(rate == 0, 0.0, duty / rate)


def _carnot_heating_cop(efficiency, lift, sink_inlet, sink_outlet, source_inlet, source_outlet):
    """Return the heating COP [-] from the Carnot fraction at the outlet temperatures [K]."""
    return efficiency * refrigeration.carnot_cop_heating(sink_outlet, source_outlet, lift)


def _carnot_cooling_cop(efficiency, lift, sink_inlet, sink_outlet, source_inlet, source_outlet):
    """Return the cooling COP [-] from the Carnot fraction at the outlet temperatures [K]."""
    return efficiency * refrigeration.carnot_cop_cooling(sink_outlet, source_outlet, lift)


def _lorenz_cop(efficiency, lift, sink_inlet, sink_outlet, source_inlet, source_outlet):
    """Return the heating COP [-] from the Lorenz fraction at the circuit glides [K]."""
    cop = refrigeration.lorenz_cop_heating(
        sink_inlet, sink_outlet, source_inlet, source_outlet, lift
    )
    return efficiency * cop


def _lorenz_surplus(outlet_T, rate, source_inlet, sink_inlet, sink_outlet, duty, efficiency, lift):
    """Return the evaporator balance C (T_in - x) - Q (1 - 1 / COP(x)) [W] at source outlet x."""
    cop = _lorenz_cop(efficiency, lift, sink_inlet, sink_outlet, source_inlet, outlet_T)
    return rate * (source_inlet - outlet_T) - duty * (1 - 1 / cop)


def _shortfall(
    cop_function, useful, sink_inlet, sink_rate, source_inlet, limit, available, efficiency, lift
):
    """Return the evaporator demand minus the available heat [W] at a COP function's COP.

    ``cop_function`` is the structural choice of the COP model (``_carnot_heating_cop`` or
    ``_lorenz_cop``); the solver binds it with ``partial`` and varies ``useful``.
    """
    sink_outlet = sink_inlet + _load(useful, sink_rate)
    cop = cop_function(efficiency, lift, sink_inlet, sink_outlet, source_inlet, limit)
    return useful * (1 - 1 / cop) - available
