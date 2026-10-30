"""A computation graph: ordered nodes, named inputs by role, named outputs and checks."""

import numbers

import numpy as np

from gemini.errors import TraceError
from gemini.graph.node import Node, caller_source
from gemini.graph.proxy import Proxy
from gemini.ops import Constant


class Graph:
    """The traced graph of one module call; nodes are kept in creation (topological) order.

    ``inputs`` maps names to input nodes, ``outputs`` maps ``outputs.<name>`` and
    ``outlets.<port>.<field>`` to the node (or literal) that computes them, ``checks`` lists the
    check nodes (their codes are their position plus one), ``constants`` the ``Constant``
    objects behind the constant inputs, ``outlet_fluids`` the fixed fluid of every outlet and
    ``observers`` the forward hooks that only read and are replayed per row after a run.
    """

    def __init__(self, module_path):
        """Start an empty graph for the module at ``module_path``."""
        self.module_path = module_path
        self.nodes = []
        self.inputs = {}
        self.outputs = {}
        self.checks = []
        self.constants = {}
        self.outlet_fluids = {}
        self.observers = []

    def input(self, name, role, unit=None, shape=()):
        """Add a named graph input and return its traced value."""
        node = self._add(Node(len(self.nodes), "input", "input", name=name, role=role))
        node.unit, node.shape = unit, shape
        self.inputs[name] = node
        return Proxy(node, self)

    def record(self, definition, operands, attributes=None):
        """Add one op node over ``operands`` and return its traced value; checks return None."""
        lifted = tuple(self._operand(operand) for operand in operands)
        node = Node(len(self.nodes), definition.name, definition.kind, operands=lifted)
        node.attributes = attributes
        node.source = caller_source()
        self._add(node)
        if definition.kind != "check":
            return Proxy(node, self)
        self._attach_check(node)
        return None

    def output(self, name, value):
        """Name a graph output; ``value`` is a traced value or a literal number."""
        self.outputs[name] = self._operand(value)

    def by_role(self, role):
        """Return the input nodes of one role by name."""
        return {name: node for name, node in self.inputs.items() if node.role == role}

    def _add(self, node):
        self.nodes.append(node)
        return node

    def _attach_check(self, node):
        """Give the check its code and attach its error to its traced message values."""
        self.checks.append(node)
        node.code = len(self.checks)
        values = node.attributes["values"]
        targets = [value.node for value in values.values() if isinstance(value, Proxy)]
        if not targets and isinstance(node.operands[0], Node):
            targets = [node.operands[0]]
        for target in targets:
            target.guards.append(node)

    def _operand(self, value):
        """Return the node of a traced value or constant, or a literal number unchanged."""
        if isinstance(value, Proxy):
            if value.graph is not self:
                raise TraceError(f"{self.module_path}: traced value of another graph")
            return value.node
        if isinstance(value, Constant):
            return self._constant(value)
        if isinstance(value, (numbers.Number, np.number, np.bool_)):
            return value
        raise TraceError(
            f"{self.module_path}: operand {value!r} of type {type(value).__name__} cannot be "
            "traced; expected a number, a traced value or a Constant"
        )

    def _constant(self, constant):
        """Return the one input node of a constant, adding it on first use."""
        if constant.name not in self.inputs:
            self.input(constant.name, "constant", constant.unit)
            self.constants[constant.name] = constant
        return self.inputs[constant.name]

    def describe(self):
        """Return a readable listing: inputs by role with units, nodes, checks and outputs."""
        lines = [f"graph of {self.module_path}", "inputs:"]
        for node in self.inputs.values():
            shape = f" shape={node.shape}" if node.shape else ""
            lines.append(f"  {node.label()} {node.role} [{node.unit or '-'}]{shape}")
        lines.append("nodes:")
        for node in self.nodes:
            if node.op != "input":
                operands = ", ".join(_describe(operand) for operand in node.operands)
                lines.append(f"  %{node.index} = {node.op}({operands})  {node.source}")
        lines.append("checks:")
        for node in self.checks:
            error = node.attributes["error"].__name__
            lines.append(f"  code {node.code}: {error} at {node.source}")
        lines.append("outputs:")
        lines.extend(f"  {name} = {_describe(value)}" for name, value in self.outputs.items())
        lines.extend(f"observer: {hook!r}" for hook in self.observers)
        return "\n".join(lines)


def _describe(operand):
    return operand.label() if isinstance(operand, Node) else repr(operand)
