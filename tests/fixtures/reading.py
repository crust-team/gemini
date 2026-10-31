"""Read a module result by the names of the quantities on its ports.

A value that crosses a port is a port quantity, not an output. The tests state their numbers by
name: ``reading(result).electricity`` is the power on ``power_in``, so each assertion keeps its
number and reads it where it now lives.
"""

from gemini.modules._utils import burner
from gemini.physics import heat_transfer, units

_PORT_POWERS = {
    "electricity": ("inlets", "power_in"),
    "electricity_generated": ("outlets", "power_out"),
}
"""Names of a power that one port carries."""


_FUEL_PARTS = ("fuel_coproduced", "fuel_purchased", "burned_mass_flow")
"""What ``burner.fuel_split`` returns of a burner, in its order."""


def _fall(first, second):
    """Return the heat [W] a stream of constant flow gives up from ``first`` to ``second``."""
    return heat_transfer.heat_rate(first.heat_capacity_rate(), first.T - second.T)


class Reading:
    """The outputs of a ``ModuleResult`` and the old names of what its ports carry."""

    def __init__(self, result, offered=None):
        """Read ``result``, of a burner offered the gas stream ``offered`` if one is given."""
        self.result = result
        self.offered = offered

    def __getattr__(self, name):
        """Return an output, else the port quantity of that name."""
        result = self.result
        if name in result.outputs:
            return result.outputs[name]
        if name in _FUEL_PARTS:
            parts = burner.fuel_split(result.outputs.fuel, self.offered)
            return parts[_FUEL_PARTS.index(name)]
        try:
            return _port_quantity(result, name)
        except (AttributeError, KeyError):
            return getattr(result.outputs, name)

    def __contains__(self, name):
        """Return whether ``name`` is an output or a port quantity."""
        try:
            getattr(self, name)
        except (AttributeError, KeyError):
            return False
        return True

    def get(self, name, default=None, *, unit=None):
        """Return a value like ``Values.get``; a port power converts from W."""
        if name in self.result.outputs:
            return self.result.outputs.get(name, default, unit=unit)
        try:
            value = _port_quantity(self.result, name)
        except (AttributeError, KeyError):
            return default
        return value if unit is None else _in_unit(value, name, unit)


def _in_unit(value, name, unit):
    quantity = "temperature" if name.endswith("_T") else "power"
    si = "K" if quantity == "temperature" else "W"
    return units.convert(value, si, unit, quantity)


def _port(result, port):
    return result.inlets[port] if port in result.inlets else result.outlets[port]


def _is_port(result, port):
    return port in result.inlets or port in result.outlets


def _loss(result):
    return result.outlets["loss_out"]


def _exchange(result, name):
    """Return a duty that two ports of a machine show, by its old name."""
    inlets, outlets = result.inlets, result.outlets
    pairs = {
        "useful_duty": None,
        "generator_duty": ("generator_in", "generator_out"),
        "evaporator_duty": ("chilled_in", "chilled_out"),
        "absorber_condenser_duty": ("cooling_out", "cooling_in"),
        "adsorber_condenser_duty": ("cooling_out", "cooling_in"),
        "condenser_duty": ("sink_out", "sink_in"),
        "charge_duty": None,
        "discharge_duty": None,
    }
    pair = pairs.get(name)
    if pair is None:
        return None
    first, second = pair
    if first not in inlets and first not in outlets:
        return None
    return _fall(_port(result, first), _port(result, second))


def _port_quantity(result, name):
    """Return the port quantity of the old output ``name``."""
    if name in _PORT_POWERS:
        section, port = _PORT_POWERS[name]
        return getattr(result, section)[port]
    if name == "heat_loss":
        return heat_transfer.signed_parts(_loss(result))[0]
    if name == "heat_absorbed" and "loss_out" in result.outlets:
        return heat_transfer.signed_parts(_loss(result))[1]
    if name.endswith("_T") and _is_port(result, name[:-2]):
        return _port(result, name[:-2]).T
    duty = _special(result, name)
    if duty is None:
        raise AttributeError(name)
    return duty


def _fall_of(result, first, second):
    return _fall(_port(result, first), _port(result, second))


def _supply_in_t(result):
    return result.inlets["supply_in"].T


def _wellhead(result):
    return result.inlets["wellhead_in"] if "wellhead_in" in result.inlets else None


_FIELDS = {
    "flow": lambda r: r.inlets["fluid_in"].volumetric_flow(),
    "gas_mass_flow": lambda r: r.outlets["gas_out"].m_dot,
    "steam_mass_flow": lambda r: r.outlets["gas_out"].m_dot,
    "blowdown_mass_flow": lambda r: r.outlets["waste_out"].m_dot,
    "product_mass_flow": lambda r: r.inlets["chemical_in"].m_dot,
    "heat_extraction_rate": lambda r: -r.outlets["loss_out"],
    "heat_input": lambda r: _fall_of(r, "fluid_in", "fluid_out"),
    "heat_recovered": lambda r: _fall_of(r, "fluid_out", "fluid_in"),
    "bottomhole_pressure": lambda r: r.outlets["bottom_out"].p,
    "bottomhole_temperature": lambda r: r.outlets["bottom_out"].T,
    "wellhead_pressure": lambda r: r.outlets["wellhead_out"].p,
    "wellhead_temperature": lambda r: (_wellhead(r) or r.outlets["wellhead_out"]).T,
    "fuel_or_power": lambda r: r.inlets["power_in"],
    "signed_duty": lambda r: _fall_of(r, "fluid_in", "fluid_out"),
    "supply_in_T": _supply_in_t,
    "temperature_difference": lambda r: _supply_in_t(r) - r.outlets["return_out"].T,
    "heat_supplied": lambda r: _fall_of(r, "supply_in", "return_out"),
    "heat_absorbed": lambda r: -_fall_of(r, "supply_in", "return_out"),
}
"""Old output names and how the ports show them."""


def _special(result, name):
    """Return a quantity that two ports show together, or one field of a port."""
    inlets = result.inlets
    if name in _FIELDS:
        return _FIELDS[name](result)
    if name == "duty" and "fluid_in" in inlets:
        return abs(_fall_of(result, "fluid_in", "fluid_out"))
    if name == "useful_duty":
        return _useful_duty(result)
    if name in ("charge_duty", "discharge_duty"):
        port = name.partition("_")[0]
        return abs(_fall_of(result, f"{port}_in", f"{port}_out"))
    if name == "evaporator_duty" and "source_in" in inlets:
        return _fall_of(result, "source_in", "source_out")
    return _exchange(result, name)


def _useful_duty(result):
    """Return what a machine delivers: to the sink of a heat pump, from the chilled water."""
    outlets, inlets = result.outlets, result.inlets
    if "sink_out" in outlets:
        return _fall(outlets["sink_out"], inlets["sink_in"])
    return _fall(inlets["chilled_in"], outlets["chilled_out"])


def reading(result, offered=None):
    """Return a reader of ``result`` by quantity."""
    return Reading(result, offered)
