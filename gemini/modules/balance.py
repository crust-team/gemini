"""Mass and sensible-energy audits over retained evaluation trees.

A leaf exchanges energy outside its streams only through these ``Power`` outputs, named the
same in every module and nonnegative except the storage term below: ``electricity`` and
``fuel`` consumed, ``heat_absorbed`` taken in from outside the plant (ambient air, a cooled
building), ``heat_loss`` lost to the environment, ``heat_supplied`` delivered to a consumer and
``electricity_generated`` produced. Storage is the one signed energy output:
``heat_accumulation`` is the rate of increase of the energy a leaf stores (positive while
charging, negative while discharging), counted as an outflow, so a storage leaf that reports it
closes like any other leaf. The legacy isothermal pumps do not allocate electricity to fluid
enthalpy, mechanical work or environmental loss. Report that unresolved energy explicitly;
never manufacture heat loss to force a first-law residual to zero.
"""

from gemini import ops
from gemini.modules.pumps import ESP, InjectionPump, LineShaftPump
from gemini.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.physics import combustion, diagnostics, heat_transfer
from gemini.types.flows import Stream

ENERGY_INPUTS = ("electricity", "fuel", "heat_absorbed")
"""Leaf outputs [W] that bring energy into a leaf from outside its streams."""

ENERGY_OUTPUTS = ("heat_loss", "heat_supplied", "electricity_generated", "heat_accumulation")
"""Leaf outputs [W] that take energy out of a leaf other than through its streams.

All are nonnegative except ``heat_accumulation``, the signed rate of change of stored energy.
"""


def collect_flows(result_tree):
    """Sum leaf energy outputs once, ignoring composite aggregate outputs [W]."""
    if isinstance(result_tree, dict):
        totals = [collect_flows(child) for child in result_tree.values()]
        return {key: sum(t[key] for t in totals) for key in ENERGY_INPUTS + ENERGY_OUTPUTS}
    if result_tree.children:
        return collect_flows(result_tree.children)
    return {key: result_tree.outputs.get(key, 0.0) for key in ENERGY_INPUTS + ENERGY_OUTPUTS}


def emissions(result_tree, fuel_factor, electricity_factor):
    """Return the CO2 emission rate [kg/s] of the fuel burnt and the grid electricity drawn.

    ``fuel * fuel_factor + max(0, electricity - electricity_generated) * electricity_factor``
    over the leaf totals of ``collect_flows``, for any plant topology. Factors are SI [kg/J]:
    divide kg/GJ by 1e9 and kg/kWh by 3.6e6. All on-site generation (``CHP``, ``ORC``, any
    ``electricity_generated``) offsets the electricity of all consumers (ESP, pumps,
    compressors, heat pumps) before grid electricity is charged, and a surplus earns no credit.
    The upstream GEMINI KPI offset only the ESP's electricity by the CHP and charged the
    injection pump in full. Fuel is
    charged on its full lower-heating-value input, also when it feeds a generator, so CHP
    electricity is not charged twice. Gas vented or flared by a ``Vent`` is reported by its own
    ``co2_emission`` output and is not included.
    """
    flows = collect_flows(result_tree)
    grid = ops.maximum(0.0, flows["electricity"] - flows["electricity_generated"])
    return combustion.emission_rate(flows["fuel"], fuel_factor, grid, electricity_factor)


def _scale(incoming, outgoing):
    """Return the larger magnitude of the two flows, at least one, to normalise a residual."""
    return ops.maximum(ops.maximum(ops.abs(incoming), ops.abs(outgoing)), 1)


def _streams(ports):
    return [value for value in ports.values() if isinstance(value, Stream)]


def _enthalpy(stream):
    return heat_transfer.heat_rate(stream.heat_capacity_rate(), stream.T)


def _internal_flux(result, measure):
    """Cancel streams actually passed between leaves in evaluation order, once per output."""
    available = {}
    internal = 0.0
    for leaf in result.leaves().values():
        for stream in _streams(leaf.inlets):
            if available.get(id(stream), 0):
                internal += measure(stream)
                available[id(stream)] -= 1
        for stream in _streams(leaf.outlets):
            available[id(stream)] = available.get(id(stream), 0) + 1
    return internal


def mass_balance(module, result):
    """Audit mass [kg/s], including explicit aquifer withdrawal/deposition boundaries."""
    if result.children:
        children = {
            path: mass_balance(module.get_submodule(path), child)
            for path, child in result.leaves().items()
        }
        incoming = sum(c["in"] for c in children.values())
        outgoing = sum(c["out"] for c in children.values())
        internal = _internal_flux(result, lambda stream: stream.m_dot)
        incoming -= internal
        outgoing -= internal
        residual = sum(c["residual"] for c in children.values())
    else:
        children = {}
        incoming, outgoing = _leaf_mass(module, result)
        residual = incoming - outgoing
    return {
        "in": incoming,
        "out": outgoing,
        "residual": residual,
        "relative_residual": diagnostics.performance_ratio(
            ops.abs(residual), _scale(incoming, outgoing)
        ),
        "modules": children,
    }


def _leaf_mass(module, result):
    """Return a leaf's mass in- and outflow, counting aquifers as open boundaries."""
    incoming = sum(s.m_dot for s in _streams(result.inlets))
    outgoing = sum(s.m_dot for s in _streams(result.outlets))
    if isinstance(module, ProductionReservoir):
        incoming += result.inputs["production_rate"]
    elif isinstance(module, InjectionReservoir):
        outgoing += sum(s.m_dot for s in _streams(result.inlets))
    return incoming, outgoing


def energy_balance(module, result):
    """Return sensible enthalpy/energy fluxes [W] and an honest sum(in)-sum(out).

    Aquifers are open source/sink boundaries. Pressure, gravity and kinetic energy
    are not represented in this thermal model. `thermal_residual` audits modeled
    thermal transfers; `residual` ALSO includes unallocated pump electricity.
    A nonzero `unresolved_power` means full energy conservation is unverified.
    """
    flows = collect_flows(result)
    if result.children:
        totals = _composite_energy(module, result)
    else:
        totals = _leaf_energy(module, result, flows)
    incoming, outgoing, residual, unresolved = (
        totals[key] for key in ("in", "out", "residual", "unresolved_power")
    )
    scale = _scale(incoming, outgoing)
    return flows | {
        "heat_delivered": totals["heat_delivered"],
        "losses": flows["heat_loss"],
        "in": incoming,
        "out": outgoing,
        "residual": residual,
        "relative_residual": diagnostics.performance_ratio(ops.abs(residual), scale),
        "unresolved_power": unresolved,
        "thermal_residual": residual - unresolved,
        "relative_thermal_residual": diagnostics.performance_ratio(
            ops.abs(residual - unresolved), scale
        ),
        "modules": totals["modules"],
    }


def _composite_energy(module, result):
    """Sum the leaf audits of a composite and cancel streams passed between its leaves."""
    children = {
        path: energy_balance(module.get_submodule(path), child)
        for path, child in result.leaves().items()
    }
    internal = _internal_flux(result, _enthalpy)
    return {
        "residual": sum(c["residual"] for c in children.values()),
        "unresolved_power": sum(c["unresolved_power"] for c in children.values()),
        "in": sum(c["in"] for c in children.values()) - internal,
        "out": sum(c["out"] for c in children.values()) - internal,
        "heat_delivered": getattr(result.outputs, "thermal_power", 0.0),
        "modules": children,
    }


def _leaf_energy(module, result, flows):
    """Audit one leaf; aquifers are open boundaries.

    NOTE(refactor): isothermal legacy pumps lack a thermodynamic work/loss model, so their
    electricity is reported as ``unresolved_power``. This term exposes missing bookkeeping; it is
    NOT a modeled heat-loss port.
    """
    incoming = sum(_enthalpy(s) for s in _streams(result.inlets))
    outgoing = sum(_enthalpy(s) for s in _streams(result.outlets))
    if isinstance(module, ProductionReservoir):
        incoming += outgoing
    elif isinstance(module, InjectionReservoir):
        outgoing += incoming
    incoming += sum(flows[key] for key in ENERGY_INPUTS)
    outgoing += sum(flows[key] for key in ENERGY_OUTPUTS)
    is_pump = isinstance(module, (ESP, InjectionPump, LineShaftPump))
    return {
        "residual": incoming - outgoing,
        "unresolved_power": flows["electricity"] if is_pump else 0.0,
        "in": incoming,
        "out": outgoing,
        "heat_delivered": getattr(result.outputs, "duty", 0.0),
        "modules": {},
    }
