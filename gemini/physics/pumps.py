"""Pump relations: TNO R11363 polynomials on the US basis, affinity-law curves, efficiencies.

Two pump models live here. The ESP and line-shaft pumps use the TNO R11363 polynomials of head
and power per stage (``head``, ``power``) on the historical US basis, with ``esp_efficiency``
as the retained US-basis efficiency. The centrifugal pump uses a quadratic head curve in SI with
a parabolic efficiency (``centrifugal_head``, ``parabolic_efficiency``). The shared relations
are the speed ratio, the hydraulic and shaft power, the motor electricity and the operating
window.
"""

from gemini import ops
from gemini.ops import Constant

from . import constants, units

ESP_MIN_EFFICIENCY_POWER = Constant(
    "ESP_MIN_EFFICIENCY_POWER",
    0.1,
    "W",
    "shaft power below which the pump is treated as stopped and its efficiency as zero",
)

LINE_SHAFT_MIN_EFFICIENCY_POWER = Constant(
    "LINE_SHAFT_MIN_EFFICIENCY_POWER",
    0.1,
    "W",
    "pump power below which the pump is treated as stopped and its efficiency as zero",
)

HYDRAULIC_POWER_PER_HEAD = units.bhp_to_w(1) / units.ft_head_to_pa(1)
"""Unit factor of the ESP efficiency: [W per bhp] over [Pa per ft of head], computed once."""

POLYNOMIAL_COEFFICIENT_COUNT = 6
"""Number of ascending coefficients of the degree-5 TNO head and power polynomials."""

RUNOUT_LOAD = 2
"""Flow over the speed-scaled best-efficiency flow [-] at which the centrifugal curve ends."""

CENTRIFUGAL_HEAD_COEFFICIENT_COUNT = 3
"""Number of coefficients ``c0, c1, c2`` of the quadratic centrifugal head curve."""

DEFAULT_BEP_FLOW = 0.04
"""Default best-efficiency flow of an ESP [m3/s] (retained GEMINI default)."""

DEFAULT_INJECTION_PUMP_EFFICIENCY = 0.7
"""Default constant overall efficiency [-] of an injection pump without a power curve."""

DEFAULT_INJECTION_PUMP_FREQUENCY = 60
"""Default drive frequency [Hz] of an injection pump, the ESP catalogue frequency."""


@ops.physics
def head(volume_flow, frequency, stages, coefficients):
    """Return pressure rise [Pa] from flow [m3/s], frequency [Hz], stages and ft coefficients.

    The polynomial sum(c_i q^i) uses q in bbl/day and gives ft of head per stage at 60 Hz;
    head scales with the square of the frequency ratio.

    Valid for the fitted flow range of the coefficients and positive frequency and stages. The
    affinity law follows Takacs, Electrical Submersible Pumps Manual (2009); the polynomial
    form is the TNO R11363 pump correlation. The builtin ``sum`` over the coefficients is kept:
    it works on floats, arrays and traced values.
    """
    q = units.m3s_to_bbl_per_day(volume_flow)
    value = stages * (frequency / constants.ESP_REFERENCE_FREQUENCY) ** 2
    value *= sum(c * q**i for i, c in enumerate(coefficients))
    return units.ft_head_to_pa(value)


@ops.physics
def power(volume_flow, frequency, stages, coefficients):
    """Return power [W] from flow [m3/s], frequency [Hz], stages and bhp coefficients.

    The polynomial sum(c_i q^i) uses q in bbl/day and gives bhp per stage at 60 Hz; power
    scales with the cube of the frequency ratio.

    Valid for the fitted flow range of the coefficients and positive frequency and stages. The
    affinity law follows Takacs, Electrical Submersible Pumps Manual (2009); the polynomial
    form is the TNO R11363 pump correlation. The builtin ``sum`` over the coefficients is kept:
    it works on floats, arrays and traced values.
    """
    q = units.m3s_to_bbl_per_day(volume_flow)
    value = stages * (frequency / constants.ESP_REFERENCE_FREQUENCY) ** 3
    value *= sum(c * q**i for i, c in enumerate(coefficients))
    return units.bhp_to_w(value)


@ops.physics
def speed_ratio(frequency, rated_frequency):
    """Return the speed ratio of a variable-speed pump.

    Parameters
    ----------
    frequency, rated_frequency : float
        Drive frequency and the frequency of the catalogue curves [Hz], positive.

    Returns
    -------
    float
        ``s = f / f_rated`` [-].

    Notes
    -----
    Pump speed is proportional to the supply frequency of an induction motor (Takacs,
    Electrical Submersible Pumps Manual, 2009, affinity laws).
    """
    return frequency / rated_frequency


@ops.physics
def centrifugal_head(flow, speed, coefficients):
    """Return the pressure rise of a centrifugal pump from its quadratic curve and the speed.

    Parameters
    ----------
    flow : float
        Volume flow Q [m3/s], nonnegative.
    speed : float
        Speed ratio s [-], from ``speed_ratio``.
    coefficients : sequence of float
        ``c0, c1, c2`` [Pa, Pa s/m3, Pa s2/m6] of the curve ``H = c0 + c1 Q + c2 Q^2`` at rated
        speed.

    Returns
    -------
    float
        ``H = c0 s^2 + c1 s Q + c2 Q^2`` [Pa].

    Notes
    -----
    The affinity laws Q ~ s and H ~ s^2 applied to the rated-speed curve; valid for speed
    ratios of about 0.5 to 1.1 (Karassik et al., Pump Handbook, 4th ed., chapter 2).
    """
    c0, c1, c2 = coefficients
    return c0 * speed**2 + c1 * speed * flow + c2 * flow**2


@ops.physics
def best_efficiency_ratio(flow, speed, best_efficiency_flow):
    """Return the flow relative to the speed-scaled best-efficiency flow.

    Parameters
    ----------
    flow : float
        Volume flow Q [m3/s].
    speed : float
        Speed ratio s [-], positive.
    best_efficiency_flow : float
        Best-efficiency flow at rated speed [m3/s], positive.

    Returns
    -------
    float
        ``x = Q / (s Q_bep)`` [-]; one at the best-efficiency point.

    Notes
    -----
    The best-efficiency flow scales with speed (affinity law Q ~ s).
    """
    return flow / (speed * best_efficiency_flow)


@ops.physics
def parabolic_efficiency(best_efficiency, load):
    """Return the hydraulic efficiency of the parabola through the origin.

    Parameters
    ----------
    best_efficiency : float
        Maximum efficiency [-] at the best-efficiency flow.
    load : float
        Flow over the speed-scaled best-efficiency flow ``x`` [-], from
        ``best_efficiency_ratio``; the curve is meaningful for 0 <= x < 2.

    Returns
    -------
    float
        ``eta = eta_bep x (2 - x)`` [-].

    Notes
    -----
    Speed-scaled quadratic efficiency curve of Ulanicki, Kahler and Coulbeck (2008), Modeling the
    efficiency and power characteristics of a pump group, J. Water Resour. Plann. Manage.
    134(1), 88-93. The 2 is the shape of the parabola (zero slope at x = 1).
    """
    return best_efficiency * load * (2 - load)


@ops.physics
def hydraulic_power(flow, head):
    """Return the power given to the liquid by a pump.

    Parameters
    ----------
    flow : float
        Volume flow Q [m3/s].
    head : float
        Pressure rise H [Pa].

    Returns
    -------
    float
        ``P_hyd = Q H`` [W].

    Notes
    -----
    Karassik et al., Pump Handbook, 4th ed., chapter 2 (water horsepower).
    """
    return flow * head


@ops.physics
def pump_efficiency(flow, head, power):
    """Return the SI efficiency of a pump from a measured or modelled power; zero when stopped.

    Parameters
    ----------
    flow : float
        Volume flow Q [m3/s].
    head : float
        Pressure rise H [Pa].
    power : float
        Pump power P [W]; below ``LINE_SHAFT_MIN_EFFICIENCY_POWER`` the efficiency is zero.

    Returns
    -------
    float
        ``eta = Q H / P`` [-].

    Notes
    -----
    Karassik et al., Pump Handbook, 4th ed., chapter 2. Not bitwise the same expression as
    ``esp_efficiency``, which keeps the US-basis factors of the retained ESP model.
    """
    return ops.where(power >= LINE_SHAFT_MIN_EFFICIENCY_POWER, flow * head / power, 0.0)


@ops.physics
def esp_efficiency(flow, head, power):
    """Return the retained US-basis ESP efficiency; zero for a stopped pump.

    Parameters
    ----------
    flow : float
        Volume flow Q [m3/s].
    head : float
        Pressure rise H [Pa].
    power : float
        Shaft power P [W]; below ``ESP_MIN_EFFICIENCY_POWER`` the efficiency is zero.

    Returns
    -------
    float
        ``eta = Q[bbl/d] / 135773 * (H / P) * (W per bhp / Pa per ft)`` [-].

    Notes
    -----
    The factor 135773 is the historical ESP efficiency factor (``ESP_EFFICIENCY_FLOW_FACTOR``);
    the result is the SI ``Q H / P`` up to that factor. ``ops.truediv`` keeps the legacy float32
    arithmetic of the ESP: a plain ``/`` by a zero power raises in the plain scalar mode, where
    this function must return the discarded branch of ``ops.where`` instead.
    """
    return ops.where(
        power < ESP_MIN_EFFICIENCY_POWER,
        0.0,
        units.m3s_to_bbl_per_day(flow)
        / constants.ESP_EFFICIENCY_FLOW_FACTOR
        * ops.truediv(head, power)
        * HYDRAULIC_POWER_PER_HEAD,
    )


@ops.physics
def is_in_operating_window(flow, minimum_flow, maximum_flow, speed):
    """Return whether a flow lies inside the speed-scaled operating window of a pump.

    Parameters
    ----------
    flow : float
        Volume flow [m3/s].
    minimum_flow, maximum_flow : float
        Window limits at rated speed [m3/s].
    speed : float
        Speed ratio [-].

    Returns
    -------
    bool
        ``s Q_min <= Q <= s Q_max``.

    Notes
    -----
    The recommended operating range scales with speed (affinity law Q ~ s; Takacs, Electrical
    Submersible Pumps Manual, 2009).
    """
    return ops.logical_and(minimum_flow * speed <= flow, flow <= maximum_flow * speed)


@ops.physics
def line_shaft_friction_power(friction_loss, depth, speed):
    """Return the mechanical friction power of a line shaft.

    Parameters
    ----------
    friction_loss : float
        Friction power per shaft length at the catalogue speed [W/m].
    depth : float
        Shaft length [m].
    speed : float
        Speed ratio [-].

    Returns
    -------
    float
        ``P_f = k L s`` [W].

    Notes
    -----
    Friction grows in proportion to speed (constant bearing friction torque), the form of the
    manufacturer tables of line-shaft friction in ANSI/HI 2.3, Rotodynamic Vertical Pumps for
    Design and Application.
    """
    return friction_loss * depth * speed
