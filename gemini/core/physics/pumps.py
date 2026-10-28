"""TNO R11363 pump polynomial correlations with the historical US-basis curves."""

from gemini.core.physics import constants, units


def head(flow, frequency, stages, coefficients):
    """Return pressure rise [Pa] from flow [m3/s], frequency [Hz], stages and ft coefficients."""
    q = units.m3s_to_bbl_per_day(flow)
    value = stages * (frequency / constants.ESP_REFERENCE_FREQUENCY) ** 2
    value *= sum(c * q**i for i, c in enumerate(coefficients))
    return units.ft_head_to_pa(value)


def power(flow, frequency, stages, coefficients):
    """Return power [W] from flow [m3/s], frequency [Hz], stages and bhp coefficients."""
    q = units.m3s_to_bbl_per_day(flow)
    value = stages * (frequency / constants.ESP_REFERENCE_FREQUENCY) ** 3
    value *= sum(c * q**i for i, c in enumerate(coefficients))
    return units.bhp_to_w(value)
