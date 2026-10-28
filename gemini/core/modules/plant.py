"""Directed plant graphs with validated ports and deterministic stream tearing."""

from gemini.core.modules.module import ChildInputs, ChildOutputs, Module
from gemini.core.types.flows import Stream
from gemini.core.types.results import ModuleResult


class GraphPlant(Module):
    """Evaluate a graph of equipment and solve feedback links by fixed-point iteration."""

    name = "graph_plant"
    category = "plant"
    description = "Connected equipment graph with explicit boundary streams."
    Inputs = ChildInputs
    Outputs = ChildOutputs

    def __init__(self, modules, links, *, name="plant", boundary=None):
        """Validate topology and derive unconnected inlet/outlet ports."""
        super().__init__()
        self._set_path(name)
        self.plant_name = name
        self.boundary = boundary or {}
        self.last_results = {}
        self.last_link_streams = {}
        for key, module in modules.items():
            self.add_module(key, module)
        self.links = [
            link.model_dump() if hasattr(link, "model_dump") else dict(link) for link in links
        ]
        incoming, outgoing = set(), set()
        for link in self.links:
            source, target = link["source"], link["target"]
            if source not in self._children or target not in self._children:
                raise ValueError(f"{self.path}: unknown link endpoint {link}")
            if link["source_port"] not in self._children[source].outlets:
                raise ValueError(f"{source}: unknown source port {link['source_port']}")
            if link["target_port"] not in self._children[target].inlets:
                raise ValueError(f"{target}: unknown target port {link['target_port']}")
            sink = (target, link["target_port"])
            if sink in incoming:
                raise ValueError(f"{target}: inlet {sink[1]} has multiple sources")
            incoming.add(sink)
            outgoing.add((source, link["source_port"]))
        self.inlets = tuple(
            f"{n}.{p}" for n, m in self.named_children() for p in m.inlets if (n, p) not in incoming
        )
        self.outlets = tuple(
            f"{n}.{p}"
            for n, m in self.named_children()
            for p in m.outlets
            if (n, p) not in outgoing
        )
        self._order, self._tears = self._sort()
        self._incoming = {
            name: [(i, link) for i, link in enumerate(self.links) if link["target"] == name]
            for name in self._children
        }

    def _sort(self):
        # DFS back edges are sufficient tears; the remaining graph is acyclic.
        active, visited, tears, order = set(), set(), set(), []
        adjacency = {name: [] for name in self._children}
        for i, link in enumerate(self.links):
            adjacency[link["source"]].append((i, link["target"]))

        def visit(name):
            active.add(name)
            for i, target in adjacency[name]:
                if target in active:
                    tears.add(i)
                elif target not in visited:
                    visit(target)
            active.remove(name)
            visited.add(name)
            order.append(name)

        for name in self._children:
            if name not in visited:
                visit(name)
        return list(reversed(order)), tears

    def _evaluate(self, inputs, streams_in, state=None, dt=None):
        unknown = inputs.root.keys() - self._children.keys()
        if unknown:
            raise ValueError(f"{self.path}: unknown child inputs {sorted(unknown)}")
        guesses = {}
        for i in self._tears:
            link = self.links[i]
            key = f"{link['target']}.{link['target_port']}"
            guesses[i] = Stream.model_validate(
                self.boundary.get("tear_streams", {}).get(key, dict(m_dot=0, T=300, p=1e5))
            )
        residuals = {}
        for iteration in range(50 if guesses else 1):
            results, next_state = {}, {}
            for name in self._order:
                child = self._children[name]
                inlet = {
                    port: streams_in[f"{name}.{port}"]
                    for port in child.inlets
                    if f"{name}.{port}" in streams_in
                }
                for i, link in self._incoming[name]:
                    inlet[link["target_port"]] = (
                        guesses[i]
                        if i in guesses
                        else results[link["source"]].streams[link["source_port"]]
                    )
                controls = inputs.root.get(name, {})
                if hasattr(controls, "model_dump"):
                    controls = controls.model_dump()
                controls = self.boundary.get("inputs", {}).get(name, {}) | controls
                if dt is not None and (child.stateful or child._children):
                    next_state[name], results[name] = child.step(
                        (state or {}).get(name), controls, inlet, dt
                    )
                else:
                    results[name] = child(controls, inlet)
            updated = {
                i: results[self.links[i]["source"]].streams[self.links[i]["source_port"]]
                for i in guesses
            }
            residuals = {
                str(i): {
                    field: abs(getattr(updated[i], field) - getattr(guesses[i], field))
                    for field in ("T", "p", "m_dot")
                }
                for i in guesses
            }
            if all(r["T"] < 1e-3 and r["p"] < 1 and r["m_dot"] < 1e-6 for r in residuals.values()):
                self.last_results = results
                self.last_link_streams = {
                    i: results[l["source"]].streams[l["source_port"]]
                    for i, l in enumerate(self.links)
                }
                outlets = {
                    key: results[key.split(".")[0]].streams[key.split(".")[1]]
                    for key in self.outlets
                }
                return next_state or state, ModuleResult(
                    self.Outputs({n: r.outputs for n, r in results.items()}), outlets
                )
            guesses = updated
        raise RuntimeError(
            f"{self.path}: tear streams failed to converge after 50 iterations; "
            f"residuals={residuals}"
        )

    def forward(self, inputs, streams_in):
        """Propagate streams in topological order, iterating only when feedback exists."""
        return self._evaluate(inputs, streams_in)[1]

    def step(self, state, inputs, streams_in, dt):
        """Advance stateful children from the same initial state on every tear iteration."""
        if dt <= 0:
            raise ValueError("dt must be positive [s]")
        inputs = self._validate_inputs(inputs)
        self._check_ports(streams_in, self.inlets, "inlet")
        return self._evaluate(inputs, streams_in, state, dt)
