"""Mass and sensible-energy audits over retained evaluation trees.

The legacy isothermal pumps do not allocate electricity to fluid enthalpy,
mechanical work or environmental loss. Report that unresolved energy explicitly;
never manufacture heat loss to force a first-law residual to zero.
"""

from gemini.core.modules.pumps import ESP, BoosterPump, InjectionPump
from gemini.core.modules.subsurface import InjectionReservoir, ProductionReservoir
from gemini.core.types.flows import Stream


def collect_flows(result_tree):
    """Sum leaf energy outputs once, ignoring composite aggregate outputs [W]."""
    if isinstance(result_tree, dict):
        totals = [collect_flows(child) for child in result_tree.values()]
        return {key: sum(t[key] for t in totals) for key in ("electricity", "fuel", "heat_loss")}
    if result_tree.children:
        return collect_flows(result_tree.children)
    totals = dict(electricity=0.0, fuel=0.0, heat_loss=0.0)
    for name in totals:
        totals[name] += result_tree.outputs.get(name, 0.0)
    return totals


def _streams(ports):
    return [value for value in ports.values() if isinstance(value, Stream)]


def _enthalpy(stream):
    return stream.m_dot * stream.fluid.properties(stream.p, stream.T).cp_l * stream.T


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
        "relative_residual": abs(residual) / max(abs(incoming), abs(outgoing), 1),
        "modules": children,
    }


def _leaf_mass(module, result):
    """Return a leaf's mass in- and outflow, counting aquifers as open boundaries."""
    incoming = sum(s.m_dot for s in _streams(result.inlets))
    outgoing = sum(s.m_dot for s in _streams(result.outlets))
    if isinstance(module, ProductionReservoir):
        incoming += result.inputs["m_dot"]
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
    scale = max(abs(incoming), abs(outgoing), 1)
    return flows | {
        "heat_delivered": totals["heat_delivered"],
        "losses": flows["heat_loss"],
        "in": incoming,
        "out": outgoing,
        "residual": residual,
        "relative_residual": abs(residual) / scale,
        "unresolved_power": unresolved,
        "thermal_residual": residual - unresolved,
        "relative_thermal_residual": abs(residual - unresolved) / scale,
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
    incoming += flows["electricity"] + flows["fuel"]
    outgoing += flows["heat_loss"]
    is_pump = isinstance(module, (ESP, InjectionPump, BoosterPump))
    return {
        "residual": incoming - outgoing,
        "unresolved_power": flows["electricity"] if is_pump else 0.0,
        "in": incoming,
        "out": outgoing,
        "heat_delivered": getattr(result.outputs, "duty", 0.0),
        "modules": {},
    }
