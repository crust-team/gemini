"""Binary organic Rankine cycle plant relations: Lorenz efficiency, capacity cap, energy balance.

The reversible work of a heat source cooled from ``T_in`` to ``T_out`` and rejected at the
condensing temperature is the Lorenz (triangular-cycle) work; the plant delivers a fraction of
it (DiPippo, R. (2007), Ideal thermal efficiency for geothermal binary plants, Geothermics 36,
276-285; DiPippo, R. (2016), Geothermal Power Plants, 4th ed., chapter 8).
"""

from dataclasses import dataclass

from gemini import ops


@ops.physics
def lorenz_efficiency(
    hot_temperature: float, cold_temperature: float, condensing_temperature: float
):
    """Return the reversible efficiency of a sensible heat glide rejected at a temperature.

    Parameters
    ----------
    hot_temperature, cold_temperature : float
        Working-fluid temperatures T_a and T_b [K] at the start and end of the heat addition,
        positive and different.
    condensing_temperature : float
        Heat rejection temperature T_c [K].

    Returns
    -------
    float
        ``1 - T_c ln(T_a / T_b) / (T_a - T_b)`` [-], that is ``1 - T_c / T_lm`` with the
        logarithmic mean ``T_lm`` of ``refrigeration.log_mean_temperature``.

    Notes
    -----
    Lorenz (1894); DiPippo (2007). The expression is not written with
    ``refrigeration.log_mean_temperature``: that function checks its arguments and returns the
    inlet for equal temperatures, while this one keeps the retained floating-point order.
    """
    return 1 - condensing_temperature * ops.log(hot_temperature / cold_temperature) / (
        hot_temperature - cold_temperature
    )


@dataclass(frozen=True)
class CycleDesign:
    """Operating point of an organic Rankine cycle on a brine stream."""

    condensing_temperature: float
    outlet_temperature: float
    cycle_efficiency: float
    processed_share: float
    is_capped: bool


@ops.physics
def cycle_design(
    brine_temperature: float,
    brine_mass_flow: float,
    brine_heat_capacity: float,
    ambient_temperature: float,
    condenser_approach: float,
    pinch: float,
    minimum_outlet_temperature: float,
    carnot_fraction: float,
    capacity: float,
) -> CycleDesign:
    """Return the design point of an air-cooled binary cycle fed by brine.

    Parameters
    ----------
    brine_temperature : float
        Brine inlet temperature T_in [K].
    brine_mass_flow : float
        Brine mass flow [kg/s], nonnegative.
    brine_heat_capacity : float
        Brine specific heat capacity [J/kg/K].
    ambient_temperature, condenser_approach : float
        Air temperature [K] and condenser approach [K].
    pinch : float
        Pinch between brine and working fluid [K], nonnegative.
    minimum_outlet_temperature : float
        Lowest allowed brine outlet temperature [K].
    carnot_fraction : float
        Second-law fraction of the Lorenz efficiency [-].
    capacity : float
        Gross power limit [W], positive.

    Returns
    -------
    CycleDesign
        ``condensing_temperature`` T_c = T_amb + approach; ``outlet_temperature`` T_out =
        max(T_min, T_c + pinch) [K]; ``cycle_efficiency`` fraction * Lorenz efficiency between
        T_in - pinch and T_out - pinch [-]; ``processed_share`` of the brine, capacity over the
        uncapped gross power when that exceeds the capacity, else one [-]; ``is_capped``.
        The efficiency, the share and the flag are zero (false) when T_in <= T_out.

    Notes
    -----
    Uncapped gross power is ``eta m cp (T_in - T_out)``. Part-load degradation is not modelled.
    DiPippo (2016), chapter 8; DiPippo (2004), Second Law assessment of binary plants,
    Geothermics 33, 565-586, for second-law fractions of about 0.3 to 0.6.
    """
    condensing_temperature = ambient_temperature + condenser_approach
    outlet_temperature = ops.maximum(minimum_outlet_temperature, condensing_temperature + pinch)
    running = brine_temperature > outlet_temperature
    reversible = lorenz_efficiency(
        brine_temperature - pinch, outlet_temperature - pinch, condensing_temperature
    )
    efficiency = carnot_fraction * reversible
    uncapped = (
        efficiency
        * brine_mass_flow
        * brine_heat_capacity
        * (brine_temperature - outlet_temperature)
    )
    is_capped = uncapped > capacity
    share = ops.where(is_capped, capacity / uncapped, 1.0)
    return CycleDesign(
        condensing_temperature=condensing_temperature,
        outlet_temperature=outlet_temperature,
        cycle_efficiency=ops.where(running, efficiency, 0.0),
        processed_share=ops.where(running, share, 0.0),
        is_capped=ops.where(running, is_capped, False),
    )


@dataclass(frozen=True)
class PlantBalance:
    """Powers [W] and efficiency of a binary plant."""

    gross_power: float
    parasitic_power: float
    electricity_generated: float
    condenser_duty: float
    heat_loss: float
    thermal_efficiency: float


@ops.physics
def plant_balance(
    heat_input: float, cycle_efficiency: float, parasitic_fraction: float
) -> PlantBalance:
    """Return the energy balance of a binary plant from its heat input.

    Parameters
    ----------
    heat_input : float
        Heat taken from the brine Q [W].
    cycle_efficiency : float
        Gross cycle efficiency [-].
    parasitic_fraction : float
        Share of the gross power used by feed pump, fans and controls [-], in [0, 1).

    Returns
    -------
    PlantBalance
        ``gross_power`` eta Q; ``parasitic_power`` f W; ``electricity_generated`` W - parasitic;
        ``condenser_duty`` Q - W; ``heat_loss`` condenser duty plus parasitic power [W];
        ``thermal_efficiency`` net power over Q [-], ``None`` without heat input.

    Notes
    -----
    First law: Q = gross + condenser duty = net + heat_loss (DiPippo 2016, chapter 8). The
    parasitic power ends as heat in the air.

    Validity: heat_input nonnegative, cycle_efficiency in [0, 1], parasitic_fraction in [0, 1);
    ``thermal_efficiency`` is ``None`` for heat_input <= 0, so no division by zero occurs.
    """
    gross_power = cycle_efficiency * heat_input
    parasitic_power = parasitic_fraction * gross_power
    electricity_generated = gross_power - parasitic_power
    condenser_duty = heat_input - gross_power
    return PlantBalance(
        gross_power=gross_power,
        parasitic_power=parasitic_power,
        electricity_generated=electricity_generated,
        condenser_duty=condenser_duty,
        heat_loss=condenser_duty + parasitic_power,
        thermal_efficiency=ops.where(heat_input > 0, electricity_generated / heat_input, None),
    )
