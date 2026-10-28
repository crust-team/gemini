"""Mass and sensible-energy audits over retained evaluation trees.

The legacy isothermal pumps do not allocate electricity to fluid enthalpy,
mechanical work or environmental loss. Report that unresolved energy explicitly;
never manufacture heat loss to force a first-law residual to zero.
"""

from gemini.core.types.flows import FuelFlow, HeatFlow, PowerFlow, Stream


def collect_flows(result_tree):
    """Sum leaf reporting ports once, ignoring repeated composite aggregate ports [W]."""
    if isinstance(result_tree, dict):
        totals = [collect_flows(child) for child in result_tree.values()]
        return {key: sum(t[key] for t in totals) for key in ("electricity", "fuel", "heat_loss")}
    if result_tree.children:
        return collect_flows(result_tree.children)
    totals = dict(electricity=0.0, fuel=0.0, heat_loss=0.0)
    for flow in result_tree.streams.values():
        if isinstance(flow, PowerFlow):
            totals["electricity"] += flow.P
        elif isinstance(flow, FuelFlow):
            totals["fuel"] += flow.P
        elif isinstance(flow, HeatFlow):
            totals["heat_loss"] += flow.Q
    return totals


def _streams(ports):
    return [value for value in ports.values() if isinstance(value, Stream)]


def _enthalpy(stream):
    return stream.m_dot * stream.fluid.properties(stream.p, stream.T).cp_l * stream.T


def mass_balance(module, result):
    """Audit mass [kg/s], including explicit aquifer withdrawal/deposition boundaries."""
    if result.children:
        children = {
            path: mass_balance(module.get_submodule(path), child)
            for path, child in result.leaves().items()
        }
        incoming = sum(c["in"] for c in children.values())
        outgoing = sum(c["out"] for c in children.values())
        residual = sum(c["residual"] for c in children.values())
    else:
        children = {}
        incoming = sum(s.m_dot for s in _streams(result.inlets))
        outgoing = sum(s.m_dot for s in _streams(result.streams))
        if module.name == "production_reservoir":
            incoming += result.inputs.m_dot
        elif module.name == "injection_reservoir":
            outgoing += sum(s.m_dot for s in _streams(result.inlets))
        residual = incoming - outgoing
    return {
        "in": incoming,
        "out": outgoing,
        "residual": residual,
        "relative_residual": abs(residual) / max(abs(incoming), abs(outgoing), 1),
        "modules": children,
    }


def energy_balance(module, result):
    """Return sensible enthalpy/energy fluxes [W] and an honest sum(in)-sum(out).

    Aquifers are open source/sink boundaries. Pressure, gravity and kinetic energy
    are not represented in this thermal model. `thermal_residual` audits modeled
    thermal transfers; `residual` ALSO includes unallocated pump electricity.
    A nonzero `unresolved_power` means full energy conservation is unverified.
    """
    flows = collect_flows(result)
    if result.children:
        children = {
            path: energy_balance(module.get_submodule(path), child)
            for path, child in result.leaves().items()
        }
        residual = sum(c["residual"] for c in children.values())
        unresolved = sum(c["unresolved_power"] for c in children.values())
        incoming = sum(c["in"] for c in children.values())
        outgoing = sum(c["out"] for c in children.values())
        heat = getattr(result.outputs, "thermal_power", 0.0)
    else:
        children = {}
        incoming = sum(_enthalpy(s) for s in _streams(result.inlets))
        outgoing = sum(_enthalpy(s) for s in _streams(result.streams))
        if module.name == "production_reservoir":
            incoming += outgoing
        elif module.name == "injection_reservoir":
            outgoing += incoming
        incoming += flows["electricity"] + flows["fuel"]
        outgoing += flows["heat_loss"]
        residual = incoming - outgoing
        # NOTE(refactor): isothermal legacy pumps lack a thermodynamic work/loss model.
        # This term exposes missing bookkeeping; it is NOT a modeled heat-loss port.
        unresolved = flows["electricity"] if module.category == "pumps" else 0.0
        heat = getattr(result.outputs, "duty", 0.0)
    scale = max(abs(incoming), abs(outgoing), 1)
    return flows | {
        "heat_delivered": heat,
        "losses": flows["heat_loss"],
        "in": incoming,
        "out": outgoing,
        "residual": residual,
        "relative_residual": abs(residual) / scale,
        "unresolved_power": unresolved,
        "thermal_residual": residual - unresolved,
        "relative_thermal_residual": abs(residual - unresolved) / scale,
        "modules": children,
    }
