"""The order in which a plant runs its modules, computed from its connections.

Modules are ordered by Kahn's algorithm; ties go to the module that appears first in the
connection list, then to child order, so the sums of a composite add in the order a handwritten
``forward`` would call. A plant child that sits in a cycle of the composite graph without a cycle
between leaves is opened: its own children become steps of the parent.
"""

import heapq
from collections import deque
from dataclasses import dataclass

from gemini.core.modules.container import ModuleDict, ModuleList
from gemini.errors import NotImplementedYet
from gemini.utils.strings import join_path

STATE = "state"


def is_plant(module):
    """Return whether ``module`` is a plant, which wires its own children."""
    return hasattr(type(module), "port_map")


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
    kind: str | None


def all_links(plant, owner=""):
    """Return the connections of ``plant`` and then of every plant below it, as ``Link``."""
    links = [
        Link(
            owner,
            _absolute(owner, split_end(item["source"])),
            _absolute(owner, split_end(item["target"])),
            item.get("kind"),
        )
        for item in plant._connections
    ]
    for path, child in members(plant, owner):
        if is_plant(child):
            links += all_links(child, path)
    return links


def _absolute(owner, end):
    return join_path(owner, end[0]), end[1]


def leaf_end(root, end, side):
    """Follow plant ports down from ``end`` to the port of a module that is not a plant."""
    path, port = end
    module = root.get_module(path)
    while is_plant(module):
        inner, port = module.port_map(side)[port]
        path = join_path(path, inner)
        module = root.get_module(path)
    return path, port


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
    if link.kind == STATE:
        return None
    source, target = _leaf(root, link, "source"), _leaf(root, link, "target")
    if source == target:
        return [source, source]
    ends = [
        (_leaf(root, item, "source"), _leaf(root, item, "target"))
        for item in all_links(root)
        if item != link and item.kind != STATE
    ]
    return find_path(ends, target, source)


def _leaf(root, link, side):
    return leaf_end(root, getattr(link, side), "outlets" if side == "source" else "inlets")[0]


def collect_nodes(module, opened, prefix=""):
    """Yield ``(path, module)`` of the steps below ``module``; opened plants give their children."""
    for path, child in members(module, prefix):
        if is_plant(child) and path in opened:
            yield from collect_nodes(child, opened, path)
        else:
            yield path, child


def node_end(root, end, side, nodes):
    """Follow plant ports of opened plants from ``end`` until it is the port of a step."""
    path, port = end
    while path not in nodes:
        inner, port = root.get_module(path).port_map(side)[port]
        path = join_path(path, inner)
    return path, port


def _node_ends(root, links, opened, nodes):
    return [
        (
            node_end(root, link.source, "outlets", nodes),
            node_end(root, link.target, "inlets", nodes),
        )
        for link in links
        if link.kind != STATE and link.owner in ({""} | opened)
    ]


def open_cycles(root, links):
    """Return the paths of the plant children to open so no plant sits in a false cycle."""
    opened = set()
    while True:
        nodes = dict(collect_nodes(root, opened))
        edges = [(s[0], t[0]) for s, t in _node_ends(root, links, opened, nodes)]
        cyclic = {
            path
            for path, module in nodes.items()
            if is_plant(module) and find_path(edges, path, path) is not None
        }
        if not cyclic:
            return opened
        opened |= cyclic


def _topological(nodes, ends):
    first = {}
    for index, (source, target) in enumerate(ends):
        first.setdefault(source[0], index)
        first.setdefault(target[0], index)
    pairs = {(source[0], target[0]) for source, target in ends}
    indegree = {path: 0 for path in nodes}
    successors = {path: [] for path in nodes}
    for source, target in sorted(pairs):
        indegree[target] += 1
        successors[source].append(target)
    position = {path: index for index, path in enumerate(nodes)}

    def priority(path):
        return (first.get(path, len(ends)), position[path], path)

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
    """One module call: where each inlet comes from, as ``("inlet", name)`` or a step port."""

    path: str
    module: object
    arguments: dict


@dataclass
class Plan:
    """The steps in call order and, per plant outlet, the step port that feeds it."""

    steps: list
    outlets: dict


def compile_plan(root):
    """Return the ``Plan`` of ``root``; a state connection cannot run yet."""
    links = all_links(root)
    if any(link.kind == STATE for link in links):
        raise NotImplementedYet(
            f"{root.path}: state connections; running a loop needs a previous-step value, "
            "which lands with scan"
        )
    opened = open_cycles(root, links)
    nodes = dict(collect_nodes(root, opened))
    ends = _node_ends(root, links, opened, nodes)
    arguments = {path: {} for path in nodes}
    for source, target in ends:
        arguments[target[0]][target[1]] = ("step", *source)
    for name, end in root.port_map("inlets").items():
        path, port = node_end(root, end, "inlets", nodes)
        arguments[path][port] = ("inlet", name)
    outlets = {
        name: node_end(root, end, "outlets", nodes)
        for name, end in root.port_map("outlets").items()
    }
    steps = [Step(path, nodes[path], arguments[path]) for path in _topological(nodes, ends)]
    return Plan(steps, outlets)
