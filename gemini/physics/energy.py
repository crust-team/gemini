"""Energy conversion through an efficiency, shared by pumps, compressors, motors and burners."""

from gemini import ops


@ops.physics
def input_power(useful_power: float, efficiency: float) -> float:
    """Return the power a converter draws for a useful power, ``P_in = P_out / eta``.

    Parameters
    ----------
    useful_power : float
        Power delivered [W]: hydraulic power of a pump, shaft power of a motor, heat of a boiler.
    efficiency : float
        Conversion efficiency in (0, 1] [-].

    Returns
    -------
    float
        Power drawn [W]: shaft power, electricity or fuel.

    Notes
    -----
    Definition of the efficiency of a steady converter, valid at the operating point the efficiency
    belongs to. Reference: Moran and Shapiro, Fundamentals of Engineering Thermodynamics, section 2.
    """
    return useful_power / efficiency


@ops.physics
def output_power(input_power_value: float, efficiency: float) -> float:
    """Return the useful power [W] of an input power, ``P = F eta``.

    Parameters
    ----------
    input_power_value : float
        Power drawn [W], nonnegative.
    efficiency : float
        Useful share of it [-], positive.

    Returns
    -------
    float
        Useful power [W].

    Notes
    -----
    Definition of an efficiency, the inverse of ``input_power``.

    Validity: Any real inputs. No division occurs.
    Source: Definition of an efficiency; no published source is needed.
    """
    return input_power_value * efficiency
