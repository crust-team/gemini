"""Discrete PID control: the error, the ideal-form command and the clamped integral.

The relations are the ideal (ISA) PID form discretised as in Astrom and Hagglund (2006,
Advanced PID Control, chapter 3): explicit rectangular integral, backward-difference derivative
on the error, and clamping (conditional integration) anti-windup.
"""

from gemini import ops


@ops.physics
def pid_error(setpoint: float, measurement: float, reverse: bool) -> float:
    """Return the control error in the sense of the controller direction.

    Parameters
    ----------
    setpoint, measurement : float
        Target and measured value of the controlled variable, in one unit.
    reverse : bool
        True for a reverse-acting controller (command rises when the measurement falls, a
        heating valve), false for a direct-acting one (a cooling valve).

    Returns
    -------
    float
        ``e = setpoint - measurement`` for reverse action, ``measurement - setpoint`` for
        direct action, in the unit of the inputs.

    Notes
    -----
    Reference: Astrom and Hagglund 2006, Advanced PID Control, chapter 3 (sign of the error
    for direct and reverse action).
    """
    return ops.where(reverse, setpoint - measurement, measurement - setpoint)


@ops.physics
def pid_derivative(
    gain: float, derivative_time: float, error_change: float, previous_step: float
) -> float:
    """Return the derivative term of the ideal PID form.

    Parameters
    ----------
    gain : float
        Proportional gain K [-].
    derivative_time : float
        Derivative time Td [s], nonnegative.
    error_change : float
        Change of the error since the previous step, ``e_k - e_(k-1)``, in the unit of the error.
    previous_step : float
        Positive length of the previous step ``h_(k-1)`` [s].

    Returns
    -------
    float
        ``D_k = K Td (e_k - e_(k-1)) / h_(k-1)``, in the unit of the error.

    Notes
    -----
    Reference: Astrom and Hagglund 2006, Advanced PID Control, chapter 3: backward difference
    of the error, unfiltered. Exact for a uniform clock.
    """
    return gain * derivative_time * error_change / previous_step


@ops.physics
def pid_command(gain: float, error: float, integral: float, derivative: float) -> float:
    """Return the unclamped command of the ideal PID form.

    Parameters
    ----------
    gain : float
        Proportional gain K [-].
    error, integral, derivative : float
        Error, integral term I_k and derivative term D_k, in command units.

    Returns
    -------
    float
        ``u = K e + I + D``, before the output limits.

    Notes
    -----
    Reference: Astrom and Hagglund 2006, Advanced PID Control, chapter 3, ideal (ISA) form
    with the integral kept as a state in command units.
    """
    return gain * error + integral + derivative


@ops.physics
def pid_integral_increment(
    gain: float, duration: float, integral_time: float, error: float
) -> float:
    """Return the increase of the integral term over one step.

    Parameters
    ----------
    gain : float
        Proportional gain K [-].
    duration : float
        Length of the step h_k [s].
    integral_time : float
        Positive integral time Ti [s].
    error : float
        Error at the start of the step, in command units.

    Returns
    -------
    float
        ``I_(k+1) - I_k = K h_k / Ti e_k``, in command units.

    Notes
    -----
    Reference: Astrom and Hagglund 2006, Advanced PID Control, chapter 3, forward
    rectangular integration.
    """
    return gain * duration / integral_time * error


@ops.physics
def anti_windup_increment(
    increment: float, unclamped: float, output_min: float, output_max: float
) -> float:
    """Return the integral increment, zero while the output is clamped and driven further out.

    Parameters
    ----------
    increment : float
        Candidate integral increment, in command units.
    unclamped : float
        Command before the output limits, in command units.
    output_min, output_max : float
        Output limits, in command units.

    Returns
    -------
    float
        ``0`` if ``unclamped >= output_max`` and ``increment > 0``, or ``unclamped <=
        output_min`` and ``increment < 0``; otherwise ``increment``.

    Notes
    -----
    Reference: Astrom and Hagglund 2006, Advanced PID Control, section on anti-windup:
    clamping (conditional integration).
    """
    winding_up = ops.logical_and(unclamped >= output_max, increment > 0)
    winding_down = ops.logical_and(unclamped <= output_min, increment < 0)
    return ops.where(ops.logical_or(winding_up, winding_down), 0.0, increment)
