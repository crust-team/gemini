"""The daily controls of a plant from its demand: an energy balance on design values.

``gm.schedule`` runs no simulation. It returns run input whose columns are named after what they
drive, the dotted path of a control or boundary or ``port.field`` of a plant inlet, so
``gm.simulate(plant, plan)`` binds them by the rule of a run: nothing is stored on the plant and no
caller writes a binding.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gemini import backends
from gemini.errors import NotImplementedYet, ValidationError
from gemini.modules.cooling import AbsorptionUnit
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.heating import Boiler, HeatPump
from gemini.modules.piping import Mixer, Splitter
from gemini.modules.plants.doublet import Doublet
from gemini.modules.plants.plan import members, split_end
from gemini.physics import constants, dispatch, units
from gemini.physics.fluid import mixture_mass_flow
from gemini.utils.strings import join_names, join_path

SOURCES = ("geothermal", "heat_pump", "boiler")
RULES = ("order", "doublet_flow", "max_brine_cooling", "operating_days")
ARRAY_BACKEND = "numpy"
"""A plan is a balance over the days, on arrays whatever backend the run takes after it."""


@dataclass(frozen=True)
class Rules:
    """The rules of a schedule in SI."""

    order: tuple
    minimum_flow: float
    maximum_flow: float
    brine_cooling: float


def _quantity(text, unit):
    """Return a number in SI or a text with a unit in ``unit``; a temperature is a difference."""
    number, given = units.parse(text) if isinstance(text, str) else (text, unit)
    return units.convert(number, given, unit, "temperature_difference" if unit == "K" else None)


def _checked_rules(rules):
    """Return the ``Rules`` of the mapping ``rules``, or raise naming what does not fit."""
    unknown = sorted(set(rules) - set(RULES))
    if unknown:
        raise ValidationError(
            f"schedule: rules = {join_names(unknown)}; expected {join_names(RULES)}",
            path="rules",
            code="unknown_name",
            suggestions=list(RULES),
        )
    if rules.get("operating_days") is not None:
        raise NotImplementedYet(
            "schedule: operating_days; the meaning of the organisers' 330 daily steps is not "
            "decided yet, so only None, every doublet on every day, runs"
        )
    order = tuple(rules.get("order", SOURCES))
    if set(order) - set(SOURCES):
        raise ValidationError(
            f"schedule: order = {order!r}; expected names of {join_names(SOURCES)}",
            path="rules.order",
            suggestions=list(SOURCES),
        )
    flow = rules["doublet_flow"]
    return Rules(
        order,
        _quantity(flow["min"], "m3/s"),
        _quantity(flow["max"], "m3/s"),
        _quantity(rules["max_brine_cooling"], "K"),
    )


def _of_type(plant, kind):
    return [(path, module) for path, module in members(plant) if isinstance(module, kind)]


def _single(plant, kind):
    """Return ``(path, module)`` of the one module of ``kind``, or ``(None, None)``."""
    found = _of_type(plant, kind)
    if len(found) > 1:
        raise ValidationError(
            f"schedule: {len(found)} modules of type {kind.__name__}; expected at most one",
            code="invalid_design",
        )
    return found[0] if found else (None, None)


def _setpoint(path, module):
    """Return the persisted ``temperature_setpoint`` of a design module, or raise saying so."""
    if not module.has_input_value("temperature_setpoint"):
        raise ValidationError(
            f"schedule: {path}.temperature_setpoint has no value; expected the supply setpoint "
            "of the design",
            path=f"{path}.temperature_setpoint",
            code="invalid_design",
        )
    return module.temperature_setpoint


def _target(plant, path, port):
    """Return the module path that the outlet ``path.port`` feeds, or ``None``."""
    end = join_path(path, port)
    targets = [item["target"] for item in plant._connections if item["source"] == end]
    return split_end(targets[0])[0] if targets else None


def _doublets_below(plant, path, doublets):
    """Return the doublets the module at ``path`` feeds, through splitters."""
    if path in doublets:
        return [path]
    if not isinstance(plant._find_submodule(path or ""), Splitter):
        return []
    return [
        doublet
        for port in ("branch1_out", "branch2_out")
        for doublet in _doublets_below(plant, _target(plant, path, port), doublets)
    ]


def _brine_splits(plant, flows):
    """Return the ``split_fraction`` columns of the splitters that share the injected brine."""
    columns = {}
    for path, _ in _of_type(plant, Splitter):
        first = _doublets_below(plant, _target(plant, path, "branch1_out"), flows)
        second = _doublets_below(plant, _target(plant, path, "branch2_out"), flows)
        if first and second:
            columns[f"{path}.split_fraction"] = dispatch.flow_share(
                sum(flows[item] for item in second), sum(flows[item] for item in first)
            )
    return columns


def _load_below(plant, path):
    """Return the module at ``path``, or the module its mixer feeds when it is a ``Mixer``."""
    if path is not None and isinstance(plant.get_module(path), Mixer):
        return _target(plant, path, "fluid_out")
    return path


def _load_splits(plant, consumer, chiller, heat, generator):
    """Return the ``split_fraction`` column of the splitter between the consumer and the chiller."""
    columns = {}
    for path, _ in _of_type(plant, Splitter):
        first = _load_below(plant, _target(plant, path, "branch1_out"))
        second = _load_below(plant, _target(plant, path, "branch2_out"))
        if {first, second} == {consumer, chiller}:
            shares = (generator, heat) if first == consumer else (heat, generator)
            columns[f"{path}.split_fraction"] = dispatch.flow_share(*shares)
    return columns


def _covered_before_geothermal(plant, rules, need):
    """Return the need left for geothermal heat after the sources ordered before it."""
    capacities = {"heat_pump": _single(plant, HeatPump)[1], "boiler": _single(plant, Boiler)[1]}
    for source in rules.order[: rules.order.index("geothermal")]:
        module = capacities[source]
        if module is not None:
            need = np.maximum(need - module.capacity, 0.0)
    return need


def _doublet_columns(plant, rules, need):
    """Return the flow of each doublet [m3/s] and the columns that drive them."""
    flows, columns = {}, {}
    for path, doublet in _of_type(plant, Doublet):
        fluid = doublet.fluid.properties(0, 0)
        heat_per_flow = fluid.rho_l * fluid.cp_l * rules.brine_cooling
        flow, need = dispatch.doublet_flow(
            need, heat_per_flow, rules.minimum_flow, rules.maximum_flow
        )
        flows[path] = flow
        columns[f"{path}.flow"] = flow
        columns[f"{path}.is_running"] = flow > 0
        columns[f"{path}.reservoir.production_rate"] = mixture_mass_flow(
            flow, doublet.fluid.gas_mass_fraction, fluid.rho_l
        )
        columns[f"{path}.esp.frequency"] = np.full_like(
            flow, float(constants.ESP_REFERENCE_FREQUENCY)
        )
    return flows, columns


def _return_flow(path, grid, heat, supply):
    """Return the ``flow`` column of a grid whose return carries ``heat`` up to ``supply``."""
    if path is None or grid.return_temperature is None:
        return {}
    specific_heat = grid.fluid.properties(0, 0).cp_l
    difference = abs(supply - grid.return_temperature)
    return {f"{path}.flow": dispatch.circuit_flow(heat, specific_heat, difference)}


def _demand_columns(demand):
    """Return the demand of the days as arrays [W], cooling zero when the column is absent."""
    if "heating_demand" not in demand:
        raise ValidationError(
            "schedule: demand has no column heating_demand", path="demand", code="missing_column"
        )
    heat = demand["heating_demand"].to_numpy(dtype=float)
    if "cooling_demand" not in demand:
        return heat, np.zeros_like(heat)
    return heat, demand["cooling_demand"].to_numpy(dtype=float)


def _heating_columns(plant, heat, generator):
    """Return the columns of the heat users, the heat pump, the boiler and the return flow."""
    columns, supply = {}, None
    path, grid = _single(plant, HeatingGrid)
    if path is not None:
        columns[f"{path}.heat_demand"] = heat
    for kind in (HeatPump, Boiler):
        unit_path, module = _single(plant, kind)
        if unit_path is not None:
            supply = _setpoint(unit_path, module)
            columns[f"{unit_path}.temperature_setpoint"] = np.full_like(heat, supply)
    if supply is not None:
        columns |= _return_flow(path, grid, heat + generator, supply)
    return columns


def _cooling_columns(plant, cool):
    """Return the columns of the cooling users, the chiller and the return flow."""
    columns = {}
    path, grid = _single(plant, CoolingGrid)
    if path is not None:
        columns[f"{path}.sensible_cooling_demand"] = cool
        columns[f"{path}.latent_cooling_demand"] = np.zeros_like(cool)
    chiller_path, chiller = _single(plant, AbsorptionUnit)
    if chiller_path is not None:
        supply = _setpoint(chiller_path, chiller)
        columns[f"{chiller_path}.temperature_setpoint"] = np.full_like(cool, supply)
        columns |= _return_flow(path, grid, cool, supply)
    return columns


def schedule(plant, demand, rules):
    """Return the run input of ``plant`` for each day of ``demand``.

    A daily energy balance on the design values, with no simulation inside. An absorption chiller
    needs the cooling demand over its ``thermal_cop`` of heat. Heat comes from the sources in
    ``rules["order"]``: geothermal heat first by default, doublets in plant order, each at the flow
    that gives the heat at no more than ``max_brine_cooling``, clipped to ``doublet_flow``, and
    below the minimum at the minimum with less cooling. The heat pump lifts to its setpoint and the
    boiler covers the rest, co-produced gas first. Unmet demand is no error: the run reports it.

    Parameters
    ----------
    plant : Plant
        The design: its ``Doublet`` children, at most one ``HeatPump``, ``Boiler``,
        ``AbsorptionUnit``, ``HeatingGrid`` and ``CoolingGrid``, with the
        ``temperature_setpoint`` of the heat pump, boiler and chiller set. Plant ports named
        ``heating_return`` and ``cooling_return`` take their temperature from
        ``plant.boundary["root_inputs"]`` and get their flow from the plan.
    demand : DataFrame
        UTC index, columns ``heating_demand`` and, optionally, ``cooling_demand`` in W.
    rules : dict
        ``order`` (names of ``SOURCES``), ``doublet_flow`` (``{min, max}``), ``max_brine_cooling``
        and ``operating_days``. Only ``None`` runs for ``operating_days``: an integer or a list of
        outage dates raises ``NotImplementedYet`` until the meaning of the organisers' 330 daily
        steps is decided.

    Returns
    -------
    DataFrame
        The index of ``demand``, the demand columns, one column per scheduled control, named after
        its dotted path, ``port.m_dot`` of the return ports, and ``boiler_duty`` and
        ``<doublet>.flow``, ``<doublet>.is_running`` for reading, in SI with units in
        ``attrs["units"]``. ``gm.simulate(plant, plan)`` needs no bindings: a run binds a control to
        a column of that name, and the schedule changes nothing on the plant.
    """
    checked = _checked_rules(rules)
    with backends.settings(backend=ARRAY_BACKEND):
        return _frame(demand, _plan_columns(plant, demand, checked))


def _plan_columns(plant, demand, checked):
    """Return the columns of the plan, computed on arrays over the days."""
    heat, cool = _demand_columns(demand)
    chiller_path, chiller = _single(plant, AbsorptionUnit)
    generator = np.zeros_like(heat) if chiller is None else cool / chiller.thermal_cop
    need = _covered_before_geothermal(plant, checked, heat + generator)
    flows, columns = _doublet_columns(plant, checked, need)
    columns |= _brine_splits(plant, flows)
    consumer, _ = _single(plant, HeatingGrid)
    columns |= _load_splits(plant, consumer, chiller_path, heat, generator)
    columns |= _heating_columns(plant, heat, generator)
    columns |= _cooling_columns(plant, cool)
    columns["boiler_duty"] = _boiler_duty(plant, checked, heat + generator, flows)
    return columns


def _boiler_duty(plant, rules, need, flows):
    """Return the heat [W] the doublets leave for the boiler, on design values."""
    heat = need.copy()
    for path, doublet in _of_type(plant, Doublet):
        fluid = doublet.fluid.properties(0, 0)
        heat -= flows[path] * fluid.rho_l * fluid.cp_l * rules.brine_cooling
    return np.maximum(heat, 0.0)


def _frame(demand, columns):
    """Return the plan as a frame on the index of ``demand`` with its units in ``attrs``."""
    data = {name: demand[name].to_numpy() for name in demand}
    frame = pd.DataFrame(data | columns, index=demand.index)
    frame.attrs["units"] = dict(demand.attrs.get("units", {}))
    return frame
