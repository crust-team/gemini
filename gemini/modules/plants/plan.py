"""The order in which a plant runs its modules, computed from its connections.

Modules are ordered by Kahn's algorithm; ties go to the module that appears first in the
connection list, then to child order, so the sums of a composite add in the order a handwritten
``forward`` would call. A plant child that sits in a cycle of the composite graph without a cycle
between leaves is opened: its own children become steps of the parent.

A connection orders its two modules by which way the value travels, not the energy. A plain one
runs the source first. On a drawn connection the taker decides the flow, so it runs first and the
source receives what was taken. An ``offered`` outlet exists before the other modules run: its
module has one step that gives the offer and one call after everything it receives.
"""

import heapq
from collections import deque
from dataclasses import dataclass

from gemini.errors import NotImplementedYet, ValidationError
from gemini.modules._utils.container import ModuleDict, ModuleList
from gemini.utils.strings import join_path

STATE = "state"


def is_plant(module):
    """Return whether ``module`` is a plant, which wires its own children."""
    return hasattr(type(module), "_port_map")


def is_group(module):
    """Return whether ``module`` only holds children."""
    return isinstance(module, (ModuleDict, ModuleList))


def split_end(text):
    """Split ``"path.port"`` into ``(path, port)``."""
    path, _, port = text.rpartition(".")
    return path, port


def members(module, prefix=""):
    """Yield ``(path, child)`` of the modules below ``module``, looking through groups."""
    for name, child in module.named_children():
        path = join_path(prefix, name)
        if is_group(child):
            yield from members(child, path)
        else:
            yield path, child


@dataclass(frozen=True)
class Link:
    """One connection with absolute ends and the path of the plant that holds it."""

    owner: str
    source: tuple
    target: tuple
    type: str | None


def all_links(plant, owner=""):
    """Return the connections of ``plant`` and then of every plant below it, as ``Link``."""
    links = [
        Link(
            owner,
            _absolute(owner, split_end(item["source"])),
            _absolute(owner, split_end(item["target"])),
            item.get("type"),
        )
        for item in plant._connections
    ]
    for path, child in members(plant, owner):
        if is_plant(child):
            links += all_links(child, path)
    return links


def _absolute(owner, end):
    return join_path(owner, end[0]), end[1]


def port_ends(value):
    """Return the ends a plant port names: one ``(path, port)`` or a list of them."""
    return value if isinstance(value, list) else [value]


def inner_ends(module, path, side, port):
    """Return the ends of plant port ``port`` of ``module`` at ``path``, as absolute ends."""
    return [
        (join_path(path, inner), inner_port)
        for inner, inner_port in port_ends(module._port_map(side)[port])
    ]


def leaf_ends(root, end, side):
    """Follow plant ports down from ``end`` to the ports of modules that are not plants."""
    path, port = end
    module = root.get_module(path)
    if not is_plant(module):
        return [end]
    return [
        leaf
        for inner in inner_ends(module, path, side, port)
        for leaf in leaf_ends(root, inner, side)
    ]


def declaration(root, end, side):
    """Return the port declaration at ``end``, an outlet or an inlet by ``side``."""
    return getattr(root.get_module(end[0]), side)()[end[1]]


def order_of(root, source, target):
    """Return the module pairs ``(first, second)`` that one connection orders."""
    outlet, inlet = declaration(root, source, "outlets"), declaration(root, target, "inlets")
    if taken_back(outlet, inlet):
        return [(target[0], source[0])]
    return [] if outlet.offered else [(source[0], target[0])]


def taken_back(outlet, inlet):
    """Return whether the taker decides the flow of a connection and its source receives it.

    A drawn stream inlet on a plain outlet is a plain connection: there is nothing to take back.
    """
    return outlet.drawn or inlet.gives or (inlet.drawn and outlet.offered)


def find_path(edges, start, goal):
    """Return the modules from ``start`` to ``goal`` along ``edges`` (at least one), or None."""
    successors = {}
    for source, target in edges:
        successors.setdefault(source, []).append(target)
    parents, queue = {}, deque([start])
    while queue:
        node = queue.popleft()
        for following in successors.get(node, ()):
            if following == goal:
                return _trace(parents, start, node, goal)
            if following not in parents:
                parents[following] = node
                queue.append(following)
    return None


def _trace(parents, start, node, goal):
    path = [goal, node]
    while path[-1] != start and path[-1] in parents:
        path.append(parents[path[-1]])
    return path[::-1]


def loop_through(root, link):
    """Return the leaf modules of a loop that ``link`` closes, or ``None``.

    The link must already be in the plant; state links never close a loop.
    """
    if link.type == STATE:
        return None
    pairs = [
        pair
        for item in all_links(root)
        if item != link and item.type != STATE
        for pair in _leaf_order(root, item)
    ]
    for first, second in _leaf_order(root, link):
        if first == second:
            return [first, first]
        loop = find_path(pairs, second, first)
        if loop is not None:
            return loop
    return None


def _leaf_order(root, link):
    """Return the order pairs of the leaves a connection joins."""
    return [
        pair
        for source in leaf_ends(root, link.source, "outlets")
        for target in leaf_ends(root, link.target, "inlets")
        for pair in order_of(root, source, target)
    ]


def collect_nodes(module, opened, prefix=""):
    """Yield ``(path, module)`` of the steps below ``module``; opened plants give their children."""
    for path, child in members(module, prefix):
        if is_plant(child) and path in opened:
            yield from collect_nodes(child, opened, path)
        else:
            yield path, child


def node_ends(root, end, side, nodes):
    """Follow plant ports of opened plants from ``end`` until they are ports of steps."""
    if end[0] in nodes:
        return [end]
    inner = inner_ends(root.get_module(end[0]), end[0], side, end[1])
    return [item for item in inner for item in node_ends(root, item, side, nodes)]


def _node_ends(root, links, opened, nodes):
    return [
        (source, target)
        for link in links
        if link.type != STATE and link.owner in ({""} | opened)
        for source in node_ends(root, link.source, "outlets", nodes)
        for target in node_ends(root, link.target, "inlets", nodes)
    ]


def open_cycles(root, links):
    """Return the paths of the plant children to open so no plant sits in a false cycle."""
    opened = set()
    while True:
        nodes = dict(collect_nodes(root, opened))
        edges = [
            pair
            for source, target in _node_ends(root, links, opened, nodes)
            for pair in order_of(root, source, target)
        ]
        cyclic = {
            path
            for path, module in nodes.items()
            if is_plant(module) and find_path(edges, path, path) is not None
        }
        if not cyclic:
            return opened
        opened |= cyclic


def _topological(nodes, ordered):
    first = {}
    for index, (source, target) in enumerate(ordered):
        first.setdefault(source, index)
        first.setdefault(target, index)
    pairs = set(ordered)
    indegree = {path: 0 for path in nodes}
    successors = {path: [] for path in nodes}
    for source, target in sorted(pairs):
        indegree[target] += 1
        successors[source].append(target)
    position = {path: index for index, path in enumerate(nodes)}

    def priority(path):
        return (first.get(path, len(ordered)), position[path], path)

    ready = [priority(path) for path in nodes if indegree[path] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        path = heapq.heappop(ready)[2]
        order.append(path)
        for following in successors[path]:
            indegree[following] -= 1
            if indegree[following] == 0:
                heapq.heappush(ready, priority(following))
    return order


@dataclass
class Step:
    """One module call: where each inlet comes from, as ``("inlet", name)`` or a step port.

    A source is ``("inlet", name)``, ``("step", path, port)`` an outlet of a call, ``("offer",
    path, port)`` an offered outlet, ``("drawn", path, port)`` the value a taker drew through its
    inlet, or ``("many", sources)``. An ``offer`` step gives the offer of its module.
    """

    path: str
    module: object
    arguments: dict
    offer: bool = False


@dataclass
class Plan:
    """The steps in call order and what feeds the plant outlets and the given plant inlets."""

    steps: list
    outlets: dict
    given: dict


def unconnected_port(path):
    """Return the error of a port with no connection and no plant name."""
    return ValidationError(
        f"{path}: unconnected port; connect it to a module or name a plant port",
        path=path,
        code="unconnected_port",
    )


def compile_plan(root):
    """Return the ``Plan`` of ``root``; a dangling port or a state connection cannot run."""
    for _, path, port in root._unconnected_ports():
        raise unconnected_port(join_path(path, port))
    links = all_links(root)
    if any(link.type == STATE for link in links):
        raise NotImplementedYet(
            f"{root.path}: state connections; running a loop needs a previous-step value, "
            "which lands with scan"
        )
    opened = open_cycles(root, links)
    nodes = dict(collect_nodes(root, opened))
    wiring = _Wiring(root, nodes)
    for source, target in _node_ends(root, links, opened, nodes):
        wiring.connect(source, target)
    for name, ends in root._port_map("inlets").items():
        wiring.plant_inlet(name, ends)
    return wiring.plan(root)


def _offer_key(path):
    """Return the name of the offer step of the module at ``path`` among the step names."""
    return f"{path}#offer"


class _Wiring:
    """The arguments and the order of the steps, built one connection at a time."""

    def __init__(self, root, nodes):
        """Start from the steps ``nodes``, each offering module with its offer step first."""
        self.root = root
        self.nodes = nodes
        self.arguments = {path: {} for path in nodes}
        self.offers = {}
        self.feeds = {}
        self.ordered = []
        self.given = {}

    def _add(self, end, value):
        """Give the port ``end`` the source ``value``; a ``many`` port lists its sources."""
        path, port = end
        ports = self.nodes[path]._inlets | self.nodes[path]._outlets
        if ports[port].many:
            sources = self.arguments[path].setdefault(port, ("many", []))
            sources[1].append(value)
            return
        self.arguments[path][port] = value

    def _feed_offer(self, target, value, first):
        """Pass ``value`` on to the offer of the target when the offer reads that inlet."""
        path, port = target
        if port in self.nodes[path].offer_inlets:
            self.feeds.setdefault(path, {})[port] = value
            self.ordered.append((first, _offer_key(path)))

    def connect(self, source, target):
        """Record one connection between two steps."""
        outlet, inlet = (
            declaration(self.root, source, "outlets"),
            declaration(self.root, target, "inlets"),
        )
        first = _offer_key(source[0]) if outlet.offered else source[0]
        drawn = taken_back(outlet, inlet)
        if outlet.offered:
            self.offers.setdefault(source[0], {})
        if not inlet.gives:
            value = ("offer" if outlet.offered else "step", *source)
            self._add(target, value)
            self._feed_offer(target, value, first)
        if drawn:
            self._add(source, ("drawn", *target))
            self.ordered.append((target[0], source[0]))
        if outlet.offered or not drawn:
            self.ordered.append((first, target[0]))

    def plant_inlet(self, name, ends):
        """Record one plant inlet: it feeds its ends, or, when they give it, sums them."""
        located = [
            item
            for end in port_ends(ends)
            for item in node_ends(self.root, end, "inlets", self.nodes)
        ]
        for end in located:
            if declaration(self.root, end, "inlets").gives:
                self.given.setdefault(name, []).append(end)
                continue
            self._add(end, ("inlet", name))
            self._feed_offer(end, ("inlet", name), None)

    def plan(self, root):
        """Return the ``Plan``: the steps in order, what feeds the plant outlets and inlets."""
        names = {}
        for path in self.nodes:
            if path in self.offers:
                names[_offer_key(path)] = path
                self.ordered.append((_offer_key(path), path))
            names[path] = path
        ordered = [pair for pair in self.ordered if pair[0] is not None and pair[1] in names]
        steps = [self._step(name, names[name]) for name in _topological(names, ordered)]
        outlets = {
            name: [
                item
                for end in port_ends(ends)
                for item in node_ends(self.root, end, "outlets", self.nodes)
            ]
            for name, ends in root._port_map("outlets").items()
        }
        return Plan(steps, outlets, self.given)

    def _step(self, name, path):
        if name == path:
            return Step(path, self.nodes[path], self.arguments[path])
        return Step(path, self.nodes[path], self.feeds.get(path, {}), offer=True)
