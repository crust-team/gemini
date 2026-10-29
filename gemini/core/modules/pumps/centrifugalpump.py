"""Variable-speed centrifugal pump with a quadratic head curve and affinity-law scaling."""

from gemini.core.modules.module import Module
from gemini.core.types import (
    Control,
    Efficiency,
    Fraction,
    Frequency,
    Inlet,
    Outlet,
    Output,
    Parameter,
    Power,
    PressureDifference,
    Stream,
    Temperature,
    VolumeFlow,
)
from gemini.errors import PhysicsRangeError


class CentrifugalPump(Module):
    """Centrifugal booster or circulation pump with affinity-law speed control.

    At the rated frequency the pressure rise follows the quadratic head curve
    ``H(Q) = c0 + c1 Q + c2 Q^2`` (``head_coeff``, H in Pa and Q in m3/s). With the speed ratio
    ``s = frequency / rated_frequency`` the affinity laws (Q ~ s, H ~ s^2) give
    ``H = c0 s^2 + c1 s Q + c2 Q^2``. The hydraulic efficiency is the parabola through the
    origin with its maximum ``best_efficiency`` at the best-efficiency flow ``s * Q_bep``:
    ``eta = eta_bep * x * (2 - x)`` with ``x = Q / (s Q_bep)``, the speed-scaled quadratic
    efficiency curve of Ulanicki, Kahler and Coulbeck (2008), "Modeling the efficiency and
    power characteristics of a pump group", J. Water Resour. Plann. Manage. 134(1), 88-93.

    Hydraulic power is ``Q H``, shaft power ``Q H / eta`` and electricity the shaft power over
    ``motor_efficiency``. The pump losses ``P_shaft - P_hydraulic`` heat the liquid,
    ``dT = (P_shaft - P_hydraulic) / (m_dot cp)``, and the motor losses leave as ``heat_loss``,
    so the model is first-law closed when the flow work ``Q H`` is counted. NOTE(refactor): the
    sensible-enthalpy audit of ``energy_balance`` excludes pressure energy, so its residual for
    this pump equals ``hydraulic_power``; the unit tests check that and the full closure.

    Assumptions: incompressible liquid at the suction density, constant heat capacity, an
    efficiency that does not change with speed (affinity laws, adequate for speed ratios of
    about 0.5 to 1.1), no leakage or recirculation. Valid on the curve between zero flow and
    the run-out: a flow at or beyond twice the scaled best-efficiency flow, or one that gives
    a negative head, raises ``PhysicsRangeError``, as does reverse flow. Zero mass flow means
    the pump is stopped: no head, no power. A running pump against a closed valve (deadhead),
    whose shaft power would heat a trapped volume without bound, is outside the steady model.
    """

    repr_fields = ("rated_frequency", "best_efficiency", "best_efficiency_flow")

    def __init__(self):
        """Declare pump design data, ports and computed performance."""
        super().__init__()

        # Parameters
        self.head_coeff = Parameter(list[float], shape=(3,), calibratable=True)
        self.rated_frequency = Parameter(Frequency)
        self.best_efficiency = Parameter(Efficiency, calibratable=True)
        self.best_efficiency_flow = Parameter(VolumeFlow, gt=0)
        self.motor_efficiency = Parameter(Efficiency)

        # Inlets
        self.suction = Inlet(Stream)

        # Controls
        self.frequency = Control(Frequency)

        # Outputs
        self.flow = Output(VolumeFlow)
        self.head = Output(PressureDifference, soft_sensor=True)
        self.hydraulic_power = Output(Power)
        self.shaft_power = Output(Power, soft_sensor=True)
        self.efficiency = Output(Fraction)
        self.electricity = Output(Power)
        self.heat_loss = Output(Power)
        self.discharge_T = Output(Temperature)

        # Outlets
        self.discharge = Outlet(Stream)

    def forward(self, inlets):
        """Raise the suction pressure by the head and heat the liquid by the pump losses."""

        # Outlets
        suction = inlets.suction
        performance = self._performance(suction)
        rise = 0.0
        if suction.m_dot > 0:
            cp = suction.fluid.properties(suction.p, suction.T).cp_l
            losses = performance["shaft_power"] - performance["hydraulic_power"]
            rise = losses / (suction.m_dot * cp)

        discharge = suction.with_(p=suction.p + performance["head"], T=suction.T + rise)

        outlets = dict(discharge=discharge)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        performance = self._performance(inlets.suction)
        for name, value in performance.items():
            setattr(self, name, value)
        self.electricity = performance["shaft_power"] / self.motor_efficiency
        self.heat_loss = self.electricity - performance["shaft_power"]
        self.discharge_T = outlets.discharge.T

    def _performance(self, suction):
        """Return flow [m3/s], head [Pa], hydraulic and shaft power [W] and efficiency [-]."""
        flow = suction.volumetric_flow()
        if flow < 0:
            raise PhysicsRangeError(
                f"{self.path}: suction volume flow = {flow} m3/s; reverse flow is unsupported"
            )
        if flow == 0:
            return dict(flow=0.0, head=0.0, hydraulic_power=0.0, shaft_power=0.0, efficiency=0.0)
        speed = self.frequency / self.rated_frequency
        c0, c1, c2 = self.head_coeff
        head = c0 * speed**2 + c1 * speed * flow + c2 * flow**2
        load = flow / (speed * self.best_efficiency_flow)
        if head < 0 or load >= 2:
            raise PhysicsRangeError(
                f"{self.path}: flow = {flow} m3/s at frequency = {self.frequency} Hz gives "
                f"head = {head} Pa at {load} times the best-efficiency flow; expected a "
                "nonnegative head below twice the best-efficiency flow (pump off its curve)"
            )
        efficiency = self.best_efficiency * load * (2 - load)
        hydraulic_power = flow * head
        return dict(
            flow=flow,
            head=head,
            hydraulic_power=hydraulic_power,
            shaft_power=hydraulic_power / efficiency,
            efficiency=efficiency,
        )
