"""The controls of a plant from its demand at each step: an energy balance on design values.

``gm.schedule`` runs no simulation. It returns run input whose columns are named after what they
drive, the dotted path of a control or boundary or ``port.field`` of a plant inlet, in the SI units
``attrs["units"]`` states, so ``gm.simulate(plant, plan)`` binds them by the rule of a run: nothing
is stored on the plant and no caller writes a binding. The demand may have any constant time step,
hourly or daily; the plan has one row per step. The role of each unit comes from the wiring,
``gemini/analysis/roles.py``.
"""

import numbers
from dataclasses import dataclass

import numpy as np
import pandas as pd

from gemini import backends
from gemini.analysis import roles
from gemini.errors import ValidationError
from gemini.modules.grids import CoolingGrid, HeatingGrid
from gemini.modules.heating import Boiler
from gemini.modules.piping import Splitter
from gemini.modules.plants._utils.plan import members, split_end
from gemini.modules.plants.doublet import Doublet
from gemini.physics import constants, dispatch, units
from gemini.physics.fluid import mixture_mass_flow
from gemini.utils.strings import join_names, join_path
from gemini.utils.time import parse_duration, to_utc_index

SOURCES = ("geothermal", "heat_pump", "boiler")
RULES = ("order", "cooling_order", "doublet_flow", "max_brine_cooling", "operating_time")
ARRAY_BACKEND = "numpy"
"""A plan is a balance over the steps, on arrays whatever backend the run takes after it."""


@dataclass(frozen=True)
class Rules:
    """The rules of a schedule in SI."""

    order: tuple
    cooling_order: tuple
    minimum_flow: float
    maximum_flow: float
    brine_cooling: float
    operating_time: pd.Timedelta | float | tuple | None


def _quantity(text, unit):
    """Return a number in SI or a text with a unit in ``unit``; a temperature is a difference."""
    number, given = units.parse(text) if isinstance(text, str) else (text, unit)
    return units.convert(number, given, unit, "temperature_difference" if unit == "K" else None)


def _checked_order(rules, name, names):
    """Return the rule ``name``, a tuple of ``names``, all of them by default."""
    order = tuple(rules.get(name, names))
    if set(order) - set(names):
        raise ValidationError(
            f"schedule: {name} = {order!r}; expected names of {join_names(names)}",
            path=f"rules.{name}",
            suggestions=list(names),
        )
    return order


def _required(rules):
    """Raise ``missing_value`` naming the first limit the schedule needs that ``rules`` lacks."""
    flow = rules.get("doublet_flow")
    wanted = {
        "doublet_flow": flow,
        "doublet_flow.min": flow.get("min") if isinstance(flow, dict) else None,
        "doublet_flow.max": flow.get("max") if isinstance(flow, dict) else None,
        "max_brine_cooling": rules.get("max_brine_cooling"),
    }
    for name, found in wanted.items():
        if found is None:
            raise ValidationError(
                f"schedule: rules.{name} = missing; expected a value, a limit has no default",
                path=f"rules.{name}",
                code="missing_value",
            )


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
    _required(rules)
    flow = rules["doublet_flow"]
    return Rules(
        _checked_order(rules, "order", SOURCES),
        _checked_order(rules, "cooling_order", roles.COOLING_KINDS),
        _quantity(flow["min"], "m3/s"),
        _quantity(flow["max"], "m3/s"),
        _quantity(rules["max_brine_cooling"], "K"),
        _operating_time(rules.get("operating_time")),
    )


def _operating_time(rule):
    """Return the rule ``operating_time``.

    ``None``; a ``Timedelta`` for a duration text; a fraction in [0, 1] as a float; or the outages
    as a tuple of ``(start, end)`` UTC timestamps, a date being its whole day.
    """
    if rule is None:
        return None
    refused = ValidationError(
        f"schedule: operating_time = {rule!r}; expected None, a duration, a fraction of the "
        "period or a list of outages",
        path="rules.operating_time",
    )
    if isinstance(rule, str):
        return _duration(rule, refused)
    if isinstance(rule, (list, tuple)):
        return tuple(_outage(item, refused) for item in rule)
    if isinstance(rule, bool) or not isinstance(rule, numbers.Real) or not 0 <= rule <= 1:
        raise refused
    return float(rule)


def _duration(text, refused):
    """Return the duration ``text`` as a ``Timedelta``, or raise ``refused``."""
    try:
        return parse_duration(text)
    except (TypeError, ValueError) as error:
        raise refused from error


def _instant(value, refused):
    """Return ``value``, a date or a time, as a UTC ``Timestamp``, or raise ``refused``."""
    try:
        return to_utc_index([value])[0]
    except (TypeError, ValueError) as error:
        raise refused from error


def _outage(item, refused):
    """Return the ``(start, end)`` of an outage: an interval, or a date as its whole UTC day."""
    if not isinstance(item, dict):
        day = _instant(item, refused).normalize()
        return day, day + pd.Timedelta(days=1)
    if set(item) != {"start", "end"}:
        raise refused
    start, end = _instant(item["start"], refused), _instant(item["end"], refused)
    if end <= start:
        raise refused
    return start, end


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


def _step(demand):
    """Return the constant time step of ``demand``, or raise when it has none."""
    steps = np.diff(to_utc_index(demand.index).as_unit("ns").asi8)
    if len(steps) == 0 or (steps != steps[0]).any():
        raise ValidationError(
            "schedule: operating_time as a duration or a fraction needs a demand of at least two "
            "rows at a constant step",
            path="rules.operating_time",
        )
    return pd.Timedelta(int(steps[0]), unit="ns")


def _running_steps(demand, rule):
    """Return the steps each doublet runs under a duration or a fraction; half a step rounds up."""
    step = _step(demand)
    steps = rule * len(demand) if isinstance(rule, float) else rule / step
    return int(np.floor(steps + 0.5))


def _lowest_demand_outages(demand, rule, paths):
    """Return the outage steps of each doublet that runs the time of ``rule`` in the demand.

    The steps of lowest total demand go to the first doublet, the lowest of the rest to the next,
    so at most one doublet is off on a step; of equal steps the earliest goes first. A duration or
    a fraction not a whole number of steps rounds to the nearest whole step.
    """
    steps = len(demand)
    running = _running_steps(demand, rule)
    count = steps - running
    if not 0 <= running <= steps:
        raise ValidationError(
            f"schedule: operating_time = {rule!r}; expected 0 to {steps} steps of the demand",
            path="rules.operating_time",
        )
    if count * len(paths) > steps:
        raise ValidationError(
            f"schedule: operating_time = {rule!r}; {len(paths)} doublets need {count} outage "
            f"steps each, more than the {steps} steps of the demand",
            path="rules.operating_time",
        )
    heat, cool = _demand_columns(demand)
    ranked = np.argsort(heat + cool, kind="stable")
    index = to_utc_index(demand.index)
    return {
        path: index[np.sort(ranked[place * count : (place + 1) * count])]
        for place, path in enumerate(paths)
    }


def _listed_outages(demand, outages, paths):
    """Return the steps of the listed ``outages`` for every doublet.

    A step is off when its time is in an outage, from its start up to its end.
    """
    index = to_utc_index(demand.index)
    off = np.zeros(len(index), dtype=bool)
    for start, end in outages:
        inside = (index >= start) & (index < end)
        if not inside.any():
            raise ValidationError(
                f"schedule: operating_time has {start.isoformat()}; expected an outage that "
                "covers a step of the demand",
                path="rules.operating_time",
            )
        off |= inside
    return dict.fromkeys(paths, index[off])


def _outage_steps(plant, demand, rule):
    """Return the outage steps of each doublet, ``{path: DatetimeIndex}``."""
    paths = [path for path, _ in _of_type(plant, Doublet)]
    if rule is None or isinstance(rule, tuple):
        return _listed_outages(demand, rule or (), paths)
    return _lowest_demand_outages(demand, rule, paths)


def _setpoint(plant, path):
    """Return the ``temperature_setpoint`` of a design module, or raise saying so."""
    name = join_path(path, "temperature_setpoint")
    setpoint = plant.input_value(name)
    if setpoint is None:
        raise ValidationError(
            f"schedule: {name} has no value; expected the supply setpoint of the design, set "
            "with plant.set_inputs",
            path=name,
            code="invalid_design",
        )
    return setpoint


def _target(plant, path, port):
    """Return the module path that the outlet ``path.port`` feeds, or ``None``."""
    target = plant.target_of(join_path(path, port))
    return split_end(target)[0] if target else None


def _doublets_below(plant, path, doublets):
    """Return the doublets the module at ``path`` feeds, through splitters."""
    if path in doublets:
        return [path]
    if path is None or not isinstance(plant.get_submodule(path), Splitter):
        return []
    return [
        doublet
        for port in ("branch1_out", "branch2_out")
        for doublet in _doublets_below(plant, _target(plant, path, port), doublets)
    ]


def _source_of(plant, path, port):
    """Return ``(path, port)`` of what feeds the inlet ``path.port``, or ``None`` for no module."""
    source = plant.source_of(join_path(path, port))
    return split_end(source) if source else None


def _inlets_behind(plant, path, port):
    """Return the stream inlets of the module at ``path`` that feed its outlet ``port``.

    An outlet follows the inlet of its own circuit (``hot_out``, ``hot_in``); otherwise the module
    has one circuit, and it follows ``fluid_in`` or the branches.
    """
    inlets = plant.get_submodule(path).inlets()
    same = f"{port.removesuffix('_out')}_in"
    if same in inlets:
        return [same]
    return [name for name in inlets if name == "fluid_in" or name.startswith("branch")]


def _doublets_above(plant, path, port, doublets, seen):
    """Return the doublets whose brine reaches the inlet ``path.port``, following the circuit."""
    source = _source_of(plant, path, port)
    if source is None or source in seen:
        return set()
    seen.add(source)
    if source[0] in doublets:
        return {source[0]}
    found = set()
    for inlet in _inlets_behind(plant, *source):
        found |= _doublets_above(plant, source[0], inlet, doublets, seen)
    return found


def _heat_pump_stopped(plant, off, rows):
    """Return, per row, whether every doublet that feeds the heat pump's source is off.

    Its source then carries no flow, which stops it in the run too; a source that no doublet feeds
    never stops it.
    """
    path, _ = roles.heat_pumps(plant)
    if path is None or not any(item.any() for item in off.values()):
        return np.zeros(rows, dtype=bool)
    feeding = _doublets_above(plant, path, "source_in", off, set())
    if not feeding:
        return np.zeros(rows, dtype=bool)
    return np.logical_and.reduce([off[doublet] for doublet in feeding])


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


def _first_load(plant, outlet, loads):
    """Return the first of ``loads`` the outlet ``outlet`` reaches, or ``None``."""
    return next((path for path in plant.feeds(outlet) if path in loads), None)


def _bypass_splits(plant, consumer, chiller, heat, generator):
    """Return the ``split_fraction`` of the splitter that sends drive water past the users.

    The drive water leaves at the setpoint, as the water of the users does, and both come back at
    the return temperature, so the flows divide as the heats do.
    """
    columns = {}
    for path, _ in _of_type(plant, Splitter):
        first = _first_load(plant, join_path(path, "branch1_out"), (consumer, chiller))
        second = _first_load(plant, join_path(path, "branch2_out"), (consumer, chiller))
        if {first, second} == {consumer, chiller}:
            shares = (generator, heat) if first == consumer else (heat, generator)
            columns[f"{path}.split_fraction"] = dispatch.flow_share(*shares)
    return columns


def _covered_before_geothermal(plant, rules, need, heat_pump_stopped):
    """Return the need left for geothermal heat after the sources ordered before it."""
    heat_pump = roles.heat_pumps(plant)[0]
    modules = {
        "heat_pump": None if heat_pump is None else plant.get_submodule(heat_pump),
        "boiler": _single(plant, Boiler)[1],
    }
    running = {"heat_pump": ~heat_pump_stopped, "boiler": True}
    for source in rules.order[: rules.order.index("geothermal")]:
        module = modules[source]
        if module is not None:
            need = np.maximum(need - module.capacity * running[source], 0.0)
    return need


def _doublet_columns(plant, rules, need, off):
    """Return the flow of each doublet [m3/s] and the columns that drive them.

    A doublet off on a step has no flow and leaves its need to the next source. Under a rule of
    ``operating_time`` a doublet runs every other step, at the minimum flow without a need.
    """
    flows, columns = {}, {}
    least = 0.0 if rules.operating_time is None else rules.minimum_flow
    for path, doublet in _of_type(plant, Doublet):
        brine = doublet.reservoir.fluid
        fluid = brine.properties(0, 0)
        heat_per_flow = fluid.rho_l * fluid.cp_l * rules.brine_cooling
        flow, left = dispatch.doublet_flow(
            need, heat_per_flow, rules.minimum_flow, rules.maximum_flow
        )
        flow = np.where(off[path], 0.0, np.maximum(flow, least))
        need = np.where(off[path], need, left)
        flows[path] = flow
        columns[f"{path}.flow"] = flow
        columns[f"{path}.is_running"] = flow > 0
        columns[f"{path}.reservoir.production_rate"] = mixture_mass_flow(
            flow, brine.gas_mass_fraction, fluid.rho_l
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
    """Return the demand of the steps as arrays [W], cooling zero when the column is absent."""
    if "heating_demand" not in demand:
        raise ValidationError(
            "schedule: demand has no column heating_demand", path="demand", code="missing_column"
        )
    heat = demand["heating_demand"].to_numpy(dtype=float)
    if "cooling_demand" not in demand:
        return heat, np.zeros_like(heat)
    return heat, demand["cooling_demand"].to_numpy(dtype=float)


def _heating_columns(plant, heat, carried):
    """Return the columns of the heat users, the heat pump, the boiler and the return flow.

    The users take ``heat``; ``carried`` is the heat of the water that passes them.
    """
    columns, supply = {}, None
    path, grid = _single(plant, HeatingGrid)
    if path is not None:
        columns[f"{path}.heat_demand"] = heat
    for unit_path in (roles.heat_pumps(plant)[0], _single(plant, Boiler)[0]):
        if unit_path is not None:
            supply = _setpoint(plant, unit_path)
            columns[f"{unit_path}.temperature_setpoint"] = np.full_like(heat, supply)
    if supply is not None:
        columns |= _return_flow(path, grid, carried, supply)
    return columns


def _cold_taken(plant, rules, cool):
    """Return ``{kind: cold}`` [W] of each cooling unit: in ``cooling_order``, up to its capacity.

    What no unit takes stays unmet, which the run reports.
    """
    units = roles.cooling_units(plant)
    kinds = [kind for kind in rules.cooling_order if kind in units]
    capacities = [plant.get_submodule(units[kind]).capacity for kind in kinds]
    return dict(zip(kinds, dispatch.units_taken(cool, capacities)))


def _in_series(plant, grid_path, units):
    """Return the paths of the cooling units in the order the chilled water meets them."""
    met = [] if grid_path is None else plant.feeds(join_path(grid_path, "return_out"))
    return sorted(units, key=lambda path: met.index(path) if path in met else len(met))


def _unit_setpoints(path, grid, chain, taken, cool, supply):
    """Return the setpoint of each cooling unit of a chain on one chilled water circuit.

    The last unit brings the water to ``supply``. A unit before it stops at the temperature that
    leaves the rest of the cold to the units after it.
    """
    setpoints = {chain[-1]: np.full_like(cool, supply)}
    if len(chain) == 1 or grid.return_temperature is None:
        return setpoints | {unit: setpoints[chain[-1]] for unit in chain}
    done = np.zeros_like(cool)
    for unit in chain[:-1]:
        done = done + taken[unit]
        setpoints[unit] = dispatch.temperature_after(
            grid.return_temperature, supply, dispatch.flow_share(done, cool - done)
        )
    return setpoints


def _cooling_columns(plant, cool, taken):
    """Return the columns of the cooling users, the cooling units and the return flow."""
    columns = {}
    path, grid = _single(plant, CoolingGrid)
    if path is not None:
        columns[f"{path}.sensible_cooling_demand"] = cool
        columns[f"{path}.latent_cooling_demand"] = np.zeros_like(cool)
    units = roles.cooling_units(plant)
    if not units:
        return columns
    chain = _in_series(plant, path, list(units.values()))
    supply = _setpoint(plant, chain[-1])
    by_path = {units[kind]: taken.get(kind, np.zeros_like(cool)) for kind in units}
    for unit, setpoint in _unit_setpoints(path, grid, chain, by_path, cool, supply).items():
        columns[f"{unit}.temperature_setpoint"] = setpoint
    return columns | _return_flow(path, grid, cool, supply)


def schedule(plant, demand, rules):
    """Return the run input of ``plant`` for each step of ``demand``.

    An energy balance of each step on the design values, with no simulation inside. Roles come from
    the wiring (``gemini/analysis/roles.py``): a unit that feeds the ``CoolingGrid`` is a cooling
    unit, a ``HeatPump`` included, which is then the compression chiller. Cooling units take
    the cold in ``rules["cooling_order"]``, each up to its capacity; what they leave is unmet, no
    error. A
    heat-driven unit needs its cold over its ``thermal_cop`` of heat, and the compression chiller
    adds electricity, its condenser heat going to its cooler. Heat comes from the sources in
    ``rules["order"]``: geothermal heat first by default, doublets in plant order, each at the flow
    that gives the heat at no more than ``max_brine_cooling``, clipped to ``doublet_flow``, and
    below the minimum at the minimum with less cooling. The heat pump lifts to its setpoint and the
    boiler covers the rest, co-produced gas first. Unmet demand is no error: the run reports it.

    ``rules["operating_time"]`` takes doublets out of service, in whole steps. A duration such as
    ``"330 d"`` or ``"7920 h"``, or a fraction of the period (a number in [0, 1]), runs each
    doublet that long, rounded to the nearest whole step; its outage steps are the steps of lowest
    total demand, heating plus cooling, the first doublet taking the lowest, the next the lowest
    left, so at most one doublet is off on a step. It needs a demand of at least two rows at a
    constant step. A list of outages takes every doublet off in each: a date is that whole UTC day,
    an interval ``{"start": ..., "end": ...}`` runs from its start up to, not including, its end.
    On an outage step a doublet has no flow and its heat goes to the next sources in ``order``, and
    a heat pump fed only by doublets that are off stops. Every other step a doublet runs, at the
    minimum flow when no need is left for it.

    Parameters
    ----------
    plant : Plant
        The design: its ``Doublet`` children, at most one unit per role and kind (a heating
        ``HeatPump``, a ``Boiler``, an absorption, an adsorption and a compression chiller) and at
        most one ``HeatingGrid`` and ``CoolingGrid``, with the ``temperature_setpoint`` of the heat
        pump, the boiler and the last cooling unit set with ``set_inputs``. ``ATESPlant`` is not
        scheduled: its three seasonal commands are inputs of a run.
        Plant ports named ``heating_return`` and ``cooling_return`` take their temperature from
        the inputs (``heating_return.T``) and get their flow from the plan.
    demand : DataFrame
        UTC index at any step, columns ``heating_demand`` and, optionally, ``cooling_demand`` in W.
    rules : dict
        ``order`` (names of ``SOURCES``), ``cooling_order`` (names of ``roles.COOLING_KINDS``,
        heat-driven first by default), ``doublet_flow`` (``{min, max}``), ``max_brine_cooling``
        and ``operating_time``: ``None`` (every doublet on every step that has a need), a
        duration, a fraction of the period or a list of outages.

    Returns
    -------
    DataFrame
        The index of ``demand``, the demand columns, one column per scheduled control, named after
        its dotted path, ``port.m_dot`` of the return ports, and ``boiler_duty``,
        ``<doublet>.flow``, ``<doublet>.is_running`` and ``<heat pump>.is_running`` for reading, in
        SI with units in ``attrs["units"]``. ``attrs["outages"]`` is
        ``{doublet path: [time]}``, the ISO time of each outage step. ``gm.simulate(plant, plan)``
        needs no bindings: a run binds a control to a column of that name, and the schedule changes
        nothing on the plant.

    Raises
    ------
    ValidationError
        A rule that does not fit; with code ``invalid_value`` an ``operating_time`` that needs more
        outage steps than the demand has, that is no duration, fraction or list, that needs a
        constant step the demand lacks, or an outage outside the demand; ``unknown_name`` for a rule
        that does not exist, such as the old ``operating_days``.
    """
    checked = _checked_rules(rules)
    outages = _outage_steps(plant, demand, checked.operating_time)
    with backends.settings(backend=ARRAY_BACKEND):
        return _frame(plant, demand, _plan_columns(plant, demand, checked, outages), outages)


def _plan_columns(plant, demand, checked, outages):
    """Return the columns of the plan, computed on arrays over the steps."""
    heat, cool = _demand_columns(demand)
    index = to_utc_index(demand.index)
    off = {path: index.isin(times) for path, times in outages.items()}
    stopped = _heat_pump_stopped(plant, off, len(demand))
    taken = _cold_taken(plant, checked, cool)
    generator = _drive_heat(plant, taken, heat)
    need = _covered_before_geothermal(plant, checked, heat + generator, stopped)
    flows, columns = _doublet_columns(plant, checked, need, off)
    columns |= _brine_splits(plant, flows)
    consumer, _ = _single(plant, HeatingGrid)
    bypass = _bypass_splits(plant, consumer, _first_driven(plant), heat, generator)
    columns |= bypass
    columns |= _heating_columns(plant, heat, heat if bypass else heat + generator)
    heat_pump = roles.heat_pumps(plant)[0]
    if heat_pump is not None:
        columns[f"{heat_pump}.is_running"] = ~stopped
    columns |= _cooling_columns(plant, cool, taken)
    columns["boiler_duty"] = _boiler_duty(plant, checked, heat + generator, flows)
    return columns


def _first_driven(plant):
    """Return the path of the first heat-driven cooling unit, or ``None``."""
    units = roles.cooling_units(plant)
    return next((units[kind] for kind in roles.HEAT_DRIVEN if kind in units), None)


def _drive_heat(plant, taken, heat):
    """Return the heat [W] the heat-driven cooling units draw for the cold they take."""
    units = roles.cooling_units(plant)
    drive = np.zeros_like(heat)
    for kind in roles.HEAT_DRIVEN:
        if kind in taken:
            drive = drive + taken[kind] / plant.get_submodule(units[kind]).thermal_cop
    return drive


def _boiler_duty(plant, rules, need, flows):
    """Return the heat [W] the doublets leave for the boiler, on design values."""
    heat = need.copy()
    for path, doublet in _of_type(plant, Doublet):
        fluid = doublet.reservoir.fluid.properties(0, 0)
        heat -= flows[path] * fluid.rho_l * fluid.cp_l * rules.brine_cooling
    return np.maximum(heat, 0.0)


def _frame(plant, demand, columns, outages):
    """Return the plan on the index of ``demand`` with its units and outages in ``attrs``.

    A column that drives an input states the SI unit of it, which wins over the unit of a binding
    of that name, so a run reads the plan in SI whatever the plant was measured in.
    """
    data = {name: demand[name].to_numpy() for name in demand}
    frame = pd.DataFrame(data | columns, index=demand.index)
    driven = {path: item.unit for path, item in plant.inputs().items() if path in columns}
    frame.attrs["units"] = dict(demand.attrs.get("units", {})) | driven
    frame.attrs["outages"] = {
        path: [time.isoformat() for time in times] for path, times in outages.items()
    }
    return frame
