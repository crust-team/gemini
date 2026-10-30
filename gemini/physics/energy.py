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
