"""Generators of the plant specs whose size is a structural argument.

A well field has a number of production and injection limbs and a district network a number of
substations. Each generator returns the format 2 spec of one size; the file in
``gemini/assets/plants/`` for the default size is exactly the generator's output.

The call order of the handwritten classes these specs replace is reproduced by the order of the
connections, because the plan breaks ties by the first appearance of a module in the connection
list. A well field produces from every limb, mixes, then injects; a network pumps, splits, serves
the substations in order, mixes the returns and passes the return pipe.
"""

from gemini.errors import ValidationError

SUBSTATIONS = {"heating": "HeatingSubstation", "cooling": "CoolingSubstation"}
"""Substation type per network service."""

PRODUCTION_LIMB = (
    ("reservoir", "ProductionReservoir"),
    ("well", "ProductionWell"),
    ("esp", "ESP"),
    ("riser", "ProductionWell"),
)
"""Name and type of the modules of a production limb, in flow order."""

INJECTION_LIMB = (("well", "InjectionWell"), ("sink", "InjectionReservoir"))
"""Name and type of the modules of an injection limb, in flow order."""

PRODUCTION_FLOW = (
    ("reservoir.sandface_out", "well.bottom_in"),
    ("well.wellhead_out", "esp.fluid_in"),
    ("esp.fluid_out", "riser.bottom_in"),
)
"""Connections inside a production limb, in flow order."""

INJECTION_FLOW = (("well.bottom_out", "sink.sandface_in"),)
"""Connections inside an injection limb."""


def _module(kind):
    return {"type": kind, "params": {}}


def _link(source, target):
    return {"source": source, "target": target}


def _numbered(kind, count):
    items = {str(index): _module(kind) for index in range(count)}
    return {"type": "ModuleList", "modules": items}


def _limbs(limb, count):
    members = {name: _module(kind) for name, kind in limb}
    items = {str(index): {"type": "ModuleDict", "modules": members} for index in range(count)}
    return {"type": "ModuleList", "modules": items}


def _flow(prefix, flow, count):
    """Return the links inside every limb of the list ``prefix``."""
    return [
        _link(f"{prefix}.{index}.{source}", f"{prefix}.{index}.{target}")
        for index in range(count)
        for source, target in flow
    ]


def _mix(prefix, sources):
    """Return ``(links, outlet)`` of a mixer cascade that joins ``sources`` in order."""
    links, running = [], sources[0]
    for index, source in enumerate(sources[1:]):
        links.append(_link(running, f"{prefix}.{index}.branch1_in"))
        links.append(_link(source, f"{prefix}.{index}.branch2_in"))
        running = f"{prefix}.{index}.fluid_out"
    return links, running


def _split(prefix, targets):
    """Return ``(links, inlet)`` of a splitter cascade that divides a flow over ``targets``.

    Splitter ``i`` sends its ``branch2_out`` to ``targets[i]`` and its ``branch1_out`` on to the
    next splitter; the last target takes what is left.
    """
    count = len(targets) - 1
    if count == 0:
        return [], targets[0]
    links = [
        _link(f"{prefix}.{index}.branch1_out", f"{prefix}.{index + 1}.fluid_in")
        for index in range(count - 1)
    ]
    links += [_link(f"{prefix}.{index}.branch2_out", targets[index]) for index in range(count)]
    links.append(_link(f"{prefix}.{count - 1}.branch1_out", targets[count]))
    return links, f"{prefix}.0.fluid_in"


def _check(**counts):
    if any(value < 1 for value in counts.values()):
        given = ", ".join(f"{name} = {value}" for name, value in counts.items())
        raise ValidationError(f"{given}; expected >= 1", code="invalid_design")


def _well_field_modules(producers, injectors):
    """Return the modules of a well field: the limbs, the junctions and the rock."""
    return {
        "producers": _limbs(PRODUCTION_LIMB, producers),
        "mixers": _numbered("Mixer", producers - 1),
        "splitters": _numbered("Splitter", injectors - 1),
        "injectors": _limbs(INJECTION_LIMB, injectors),
        "formation": {"type": "Formation", "params": {}},
    }


def _well_losses(producers, injectors):
    """Return the connections of every well's heat loss to the formation."""
    wells = [
        *(f"producers.{index}.{well}" for index in range(producers) for well in ("well", "riser")),
        *(f"injectors.{index}.well" for index in range(injectors)),
    ]
    return [{"source": f"{well}.loss_out", "target": "formation.heat_in"} for well in wells]


def _one_or_list(ends):
    """Return the ends of a plant port as the spec writes them: one end alone is not a list."""
    return ends[0] if len(ends) == 1 else ends


def multi_well_spec(producers=2, injectors=1):
    """Return the spec of a well field of ``producers`` and ``injectors`` limbs.

    Each production limb is a ``ModuleDict`` of ``reservoir``, ``well``, ``esp`` and ``riser``
    and each injection limb of ``well`` and ``sink``, in the lists ``producers`` and
    ``injectors``. The risers join through ``producers - 1`` mixers and the return divides over
    ``injectors - 1`` splitters. Ports: ``return_in``, ``power_in``, ``supply_out``. Output:
    ``supply_out_T``.
    """
    _check(producers=producers, injectors=injectors)
    mixing, supply = _mix("mixers", [f"producers.{i}.riser.wellhead_out" for i in range(producers)])
    splitting, return_in = _split(
        "splitters", [f"injectors.{index}.well.wellhead_in" for index in range(injectors)]
    )
    joined = (
        "producers.0.riser.wellhead_out" if producers == 1 else f"mixers.{producers - 2}.fluid_out"
    )
    temperature = {"of": joined, "field": "T"}
    return {
        "format": 2,
        "name": "MultiWellPlant",
        "modules": _well_field_modules(producers, injectors),
        "connections": (
            _flow("producers", PRODUCTION_FLOW, producers)
            + mixing
            + _flow("injectors", INJECTION_FLOW, injectors)
            + splitting
            + _well_losses(producers, injectors)
        ),
        "inlets": {
            "return_in": return_in,
            "power_in": _one_or_list(
                [f"producers.{index}.esp.power_in" for index in range(producers)]
            ),
        },
        "outlets": {"supply_out": supply},
        "outputs": {
            "supply_out_T": temperature,
        },
        "bindings": {},
        "param_history": {},
    }


def _network_modules(consumers, service):
    """Return the modules of a network: the pump, the pipes and the substations with junctions."""
    return {
        "pump": _module("CentrifugalPump"),
        "supply_pipe": _module("Pipe"),
        "splitters": _numbered("Splitter", consumers - 1),
        "substations": _numbered(SUBSTATIONS[service], consumers),
        "mixers": _numbered("Mixer", consumers - 1),
        "return_pipe": _module("Pipe"),
    }


def district_network_spec(consumers=2, service="heating"):
    """Return the spec of a two-pipe network feeding ``consumers`` parallel substations.

    Flow order: ``pump`` -> ``supply_pipe`` -> ``splitters`` -> ``substations`` -> ``mixers`` ->
    ``return_pipe``. ``service`` is ``"heating"`` (``HeatingSubstation`` children) or
    ``"cooling"`` (``CoolingSubstation`` children). Ports: ``supply_in``, ``return_out``.
    Output: ``return_out_T``; ``power_in`` and ``loss_out`` are plant ports.
    """
    if service not in SUBSTATIONS:
        raise ValidationError(
            f"service = {service!r}; expected 'heating' or 'cooling'", code="invalid_design"
        )
    _check(consumers=consumers)
    splitting, feed = _split(
        "splitters", [f"substations.{index}.supply_in" for index in range(consumers)]
    )
    mixing, returned = _mix(
        "mixers", [f"substations.{index}.return_out" for index in range(consumers)]
    )
    return {
        "format": 2,
        "name": "DistrictNetwork",
        "modules": _network_modules(consumers, service),
        "connections": (
            [_link("pump.fluid_out", "supply_pipe.fluid_in"), _link("supply_pipe.fluid_out", feed)]
            + splitting
            + mixing
            + [_link(returned, "return_pipe.fluid_in")]
        ),
        "inlets": {
            "supply_in": "pump.fluid_in",
            "power_in": "pump.power_in",
            "air_in": ["supply_pipe.air_in", "return_pipe.air_in"],
        },
        "outlets": {
            "return_out": "return_pipe.fluid_out",
            "loss_out": ["pump.loss_out", "supply_pipe.loss_out", "return_pipe.loss_out"],
        },
        "outputs": _network_outputs(service),
        "bindings": {},
        "param_history": {},
    }


def _network_outputs(service):
    return {"return_out_T": {"of": "return_pipe.fluid_out", "field": "T"}}
