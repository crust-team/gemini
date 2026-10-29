"""TNO R11363 pump polynomial correlations with the historical US-basis curves."""

from . import constants, units


def head(volume_flow, frequency, stages, coefficients):
    """Return pressure rise [Pa] from flow [m3/s], frequency [Hz], stages and ft coefficients.

    The polynomial sum(c_i q^i) uses q in bbl/day and gives ft of head per stage at 60 Hz;
    head scales with the square of the frequency ratio.
    """
    q = units.m3s_to_bbl_per_day(volume_flow)
    value = stages * (frequency / constants.ESP_REFERENCE_FREQUENCY) ** 2
    value *= sum(c * q**i for i, c in enumerate(coefficients))
    return units.ft_head_to_pa(value)


def power(volume_flow, frequency, stages, coefficients):
    """Return power [W] from flow [m3/s], frequency [Hz], stages and bhp coefficients.

    The polynomial sum(c_i q^i) uses q in bbl/day and gives bhp per stage at 60 Hz; power
    scales with the cube of the frequency ratio.
    """
    q = units.m3s_to_bbl_per_day(volume_flow)
    value = stages * (frequency / constants.ESP_REFERENCE_FREQUENCY) ** 3
    value *= sum(c * q**i for i, c in enumerate(coefficients))
    return units.bhp_to_w(value)
