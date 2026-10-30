"""Generators of the plant specs whose size is a structural argument.

A well field has a number of production and injection limbs and a district network a number of
substations. Each generator returns the format 2 spec of one size; the file shipped in ``specs/``
for the default size is exactly the generator's output.

The call order of the handwritten classes these specs replace is reproduced by the order of the
connections, because the plan breaks ties by the first appearance of a module in the connection
list. A well field produces from every limb, mixes, then injects; a network pumps, splits, serves
the substations in order, mixes the returns and passes the return pipe.
"""

from gemini.errors import ConfigurationError

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
    ("reservoir.sandface", "well.bottom"),
    ("well.wellhead", "esp.suction"),
    ("esp.discharge", "riser.bottom"),
)
"""Connections inside a production limb, in flow order."""

INJECTION_FLOW = (("well.bottom", "sink.sandface"),)
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
        links.append(_link(running, f"{prefix}.{index}.first_in"))
        links.append(_link(source, f"{prefix}.{index}.second_in"))
        running = f"{prefix}.{index}.mixed_out"
    return links, running


def _split(prefix, targets):
    """Return ``(links, inlet)`` of a splitter cascade that divides a flow over ``targets``.

    Splitter ``i`` sends its ``second_out`` to ``targets[i]`` and its ``first_out`` on to the next
    splitter; the last target takes what is left.
    """
    count = len(targets) - 1
    if count == 0:
        return [], targets[0]
    links = [
        _link(f"{prefix}.{index}.first_out", f"{prefix}.{index + 1}.feed_in")
        for index in range(count - 1)
    ]
    links += [_link(f"{prefix}.{index}.second_out", targets[index]) for index in range(count)]
    links.append(_link(f"{prefix}.{count - 1}.first_out", targets[count]))
    return links, f"{prefix}.0.feed_in"


def _check(**counts):
    if any(value < 1 for value in counts.values()):
        given = ", ".join(f"{name} = {value}" for name, value in counts.items())
        raise ConfigurationError(f"{given}; expected >= 1")


def multi_well_spec(producers=2, injectors=1):
    """Return the spec of a well field of ``producers`` and ``injectors`` limbs.

    Each production limb is a ``ModuleDict`` of ``reservoir``, ``well``, ``esp`` and ``riser``
    and each injection limb of ``well`` and ``sink``, in the lists ``producers`` and
    ``injectors``. The risers join through ``producers - 1`` mixers and the return divides over
    ``injectors - 1`` splitters. Ports: ``return_in``, ``supply_out``. Outputs: ``electricity``,
    ``heat_loss`` and ``supply_out_T``.
    """
    _check(producers=producers, injectors=injectors)
    mixing, supply = _mix("mixers", [f"producers.{i}.riser.wellhead" for i in range(producers)])
    splitting, return_in = _split(
        "splitters", [f"injectors.{index}.well.wellhead" for index in range(injectors)]
    )
    temperature = (
        "producers.0.riser.wellhead_temperature"
        if producers == 1
        else f"mixers.{producers - 2}.mixed_out_T"
    )
    return {
        "format": 2,
        "name": "MultiWellPlant",
        "modules": {
            "producers": _limbs(PRODUCTION_LIMB, producers),
            "mixers": _numbered("Mixer", producers - 1),
            "splitters": _numbered("Splitter", injectors - 1),
            "injectors": _limbs(INJECTION_LIMB, injectors),
        },
        "connections": (
            _flow("producers", PRODUCTION_FLOW, producers)
            + mixing
            + _flow("injectors", INJECTION_FLOW, injectors)
            + splitting
        ),
        "inlets": {"return_in": return_in},
        "outlets": {"supply_out": supply},
        "outputs": {
            "electricity": {"sum": "electricity"},
            "heat_loss": {"sum": "heat_loss"},
            "supply_out_T": {"of": temperature},
        },
        "bindings": {},
        "param_history": {},
    }


def district_network_spec(consumers=2, service="heating"):
    """Return the spec of a two-pipe network feeding ``consumers`` parallel substations.

    Flow order: ``pump`` -> ``supply_pipe`` -> ``splitters`` -> ``substations`` -> ``mixers`` ->
    ``return_pipe``. ``service`` is ``"heating"`` (``HeatingSubstation`` children) or
    ``"cooling"`` (``CoolingSubstation`` children). Ports: ``supply_in``, ``return_out``.
    Outputs: ``heat_supplied`` (heating only), ``heat_absorbed``, ``heat_loss``,
    ``electricity`` and ``return_out_T``.
    """
    if service not in SUBSTATIONS:
        raise ConfigurationError(f"service = {service!r}; expected 'heating' or 'cooling'")
    _check(consumers=consumers)
    splitting, feed = _split(
        "splitters", [f"substations.{index}.network_in" for index in range(consumers)]
    )
    mixing, returned = _mix(
        "mixers", [f"substations.{index}.network_out" for index in range(consumers)]
    )
    return {
        "format": 2,
        "name": "DistrictNetwork",
        "modules": {
            "pump": _module("CentrifugalPump"),
            "supply_pipe": _module("Pipe"),
            "splitters": _numbered("Splitter", consumers - 1),
            "substations": _numbered(SUBSTATIONS[service], consumers),
            "mixers": _numbered("Mixer", consumers - 1),
            "return_pipe": _module("Pipe"),
        },
        "connections": (
            [_link("pump.discharge", "supply_pipe.inlet"), _link("supply_pipe.outlet", feed)]
            + splitting
            + mixing
            + [_link(returned, "return_pipe.inlet")]
        ),
        "inlets": {"supply_in": "pump.suction"},
        "outlets": {"return_out": "return_pipe.outlet"},
        "outputs": _network_outputs(service),
        "bindings": {},
        "param_history": {},
    }


def _network_outputs(service):
    sums = ["heat_supplied"] if service == "heating" else []
    outputs = {name: {"sum": name} for name in (*sums, "heat_absorbed", "heat_loss", "electricity")}
    return outputs | {"return_out_T": {"of": "return_pipe.outlet_T"}}
