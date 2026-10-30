"""What the absorption and adsorption machines share: circuit rates, outlets, outputs, capacity."""

from gemini import ops
from gemini.core.physics import refrigeration
from gemini.errors import PhysicsRangeError


def rates(path, inlets):
    """Return each inlet's heat capacity rate m_dot * cp [W/K]; reject negative flow."""
    rate_of = {}
    for port, stream in inlets.items():
        ops.check(
            stream.m_dot >= 0,
            PhysicsRangeError,
            "{path}: {port}.m_dot = {m_dot} kg/s; expected >= 0",
            path=path,
            port=port,
            m_dot=stream.m_dot,
        )
        rate_of[port] = stream.heat_capacity_rate()
    return rate_of


def outlet_T(stream, rate, duty):
    """Return the outlet temperature [K] after adding ``duty`` [W] at capacity rate ``rate``."""
    return ops.where(duty == 0, stream.T, stream.T + duty / rate)


def outlet_streams(inlets, values):
    """Return the generator, chilled and cooling streams at ``values``."""
    return (
        inlets.generator_in.with_(T=values["generator_out_T"]),
        inlets.chilled_in.with_(T=values["chilled_out_T"]),
        inlets.cooling_in.with_(T=values["cooling_out_T"]),
    )


def assign_outputs(module, inlets, outlets, values):
    """Set the performance ``values`` as outputs and the driving temperature difference."""
    for name, value in values.items():
        setattr(module, name, value)
    module.driving_temperature_difference = refrigeration.characteristic_temperature_difference(
        (inlets.generator_in.T + outlets.generator_out.T) / 2,
        (inlets.cooling_in.T + outlets.cooling_out.T) / 2,
        (inlets.chilled_in.T + outlets.chilled_out.T) / 2,
        module.rejection_coefficient,
        module.evaporator_coefficient,
    )


def evaporator_capacity(module, inlets, rates):
    """Return the evaporator duty [W] of the characteristic equation at these inlets."""
    return refrigeration.sorption_evaporator_capacity(
        inlets.generator_in.T,
        inlets.cooling_in.T,
        inlets.chilled_in.T,
        rates["generator_in"],
        rates["cooling_in"],
        rates["chilled_in"],
        slope=module.characteristic_slope,
        minimum_driving_difference=module.minimum_driving_difference,
        rejection_coefficient=module.rejection_coefficient,
        evaporator_coefficient=module.evaporator_coefficient,
        thermal_cop=module.thermal_cop,
        auxiliary_power_ratio=module.auxiliary_power_ratio,
    )
