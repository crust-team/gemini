"""One run of a plant: the values of its steps while ``Plant.forward`` goes through them."""

from gemini.modules.plants._utils import constraints, loops
from gemini.modules.plants._utils.plan import Loop, Solve
from gemini.utils.strings import split_path


class Run:
    """The results of one plant call so far, and how to call the next step."""

    def __init__(self, plant, inlets):
        """Start the call of ``plant`` on ``inlets``."""
        self.plant = plant
        self.inlets = inlets
        self.nodes = plant._compiled().nodes
        self.results = {}
        self.offers = {}
        self.tears = {}
        self.overrides = {}

    def value(self, source):
        """Return what a source of ``Step.arguments`` holds now."""
        kind = source[0]
        if kind == "many":
            return [self.value(item) for item in source[1]]
        if kind == "inlet":
            return self.inlets[source[1]]
        if kind == "tear":
            return self.tears[source[1]]
        if kind == "offer":
            return self.offers[source[1]][source[2]]
        if kind == "drawn":
            return self.results[source[1]].inlets[source[2]]
        return self.results[source[1]].outlets[source[2]]

    def outlet(self, end):
        """Return the value of the outlet ``end``, ``(path, port)``, in the last call."""
        return self.results[end[0]].outlets[end[1]]

    def _is_known(self, source):
        kind = source[0]
        if kind == "offer":
            return source[1] in self.offers
        return kind == "inlet" or (kind == "step" and source[1] in self.results)

    def known_arguments(self, step):
        """Return the arguments of ``step`` that exist already: what comes from outside a loop."""
        return {
            port: self.value(source)
            for port, source in step.arguments.items()
            if self._is_known(source)
        }

    def call(self, step, trial=False):
        """Call one step; a trial is recorded by no running call."""
        arguments = {port: self.value(source) for port, source in step.arguments.items()}
        if step.offer:
            self.offers[step.path] = step.module.offer(arguments)
            return
        arguments |= self.overrides.get(step.path, {})
        call = step.module._trial if trial else step.module
        self.results[step.path] = call(**arguments)

    def execute(self, item):
        """Run one item of the plan: a step, a loop or a constraint."""
        if isinstance(item, Loop):
            loops.close(self, item)
        elif isinstance(item, Solve):
            constraints.solve(self, item)
        else:
            self.call(item)

    def read(self, path):
        """Return the value at a dotted path, an output or a port field of a step or a declaration.

        ``riser.bottomhole_pressure`` is an output, ``riser.wellhead_out.p`` a field of a port, and
        what names no step is a parameter, control or boundary of the plant or of a child.
        """
        owner, name = split_path(path)
        if owner in self.results:
            return self.results[owner].outputs[name]
        step, port = split_path(owner)
        if step in self.results:
            result = self.results[step]
            ports = result.outlets if port in result.outlets else result.inlets
            return getattr(ports[port], name)
        if step in self.nodes and port in self.plan_arguments(step):
            return getattr(self.value(self.plan_arguments(step)[port]), name)
        return getattr(self.plant.get_submodule(owner), name)

    def plan_arguments(self, path):
        """Return the arguments of the step at ``path``."""
        return self.plant._compiled().arguments[path]
