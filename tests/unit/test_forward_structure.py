"""Enforce fluid-only forwards and leaf/composite output conventions."""

import ast
import inspect
import io
import textwrap
import tokenize

from examples.shared.doublet_heat.plant import DoubletHeatPlant  # noqa: F401
from gemini.core.modules.module import MODULE_REGISTRY, Module
from gemini.core.modules.plants import Doublet  # noqa: F401
from gemini.core.types import Stream

FORWARD_SECTIONS = ("# Modules", "# Outlets")
INIT_SECTIONS = (
    "# Modules",
    "# Parameters",
    "# Inlets",
    "# Controls",
    "# Boundaries",
    "# States",
    "# Outputs",
    "# Outlets",
)


def _source_tree(method):
    source = textwrap.dedent(inspect.getsource(method))
    return source, ast.parse(source).body[0]


def _comments(source):
    return [
        (token.string.strip(), token.start[0])
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]


def _assert_ordered_sections(cls, source, allowed):
    sections = [(comment, line) for comment, line in _comments(source) if comment in allowed]
    mentioned = [name for name, _ in sections]
    assert mentioned == [
        name for name in allowed if name in mentioned
    ], f"{cls.__name__}: sections are out of order"
    for comment, _ in _comments(source):
        if comment.startswith("# ") and comment.split(":", 1)[0] in INIT_SECTIONS:
            assert comment in allowed, f"{cls.__name__}: invalid section {comment!r}"


def _self_assignments(tree):
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        found.extend(
            target.attr
            for target in targets
            if isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        )
    return found


def _assert_return_block(cls, tree, outlet_names):
    assignment, returned = tree.body[-2:]
    assert (
        isinstance(assignment, ast.Assign)
        and isinstance(assignment.value, ast.Call)
        and isinstance(assignment.value.func, ast.Name)
        and assignment.value.func.id == "dict"
        and isinstance(returned, ast.Return)
        and isinstance(returned.value, ast.Name)
        and returned.value.id == "outlets"
    ), f"{cls.__name__}: forward must end with outlets = dict(...); return outlets"
    keys = [keyword.arg for keyword in assignment.value.keywords]
    assert keys == outlet_names, f"{cls.__name__}: outlet order {keys} != {outlet_names}"


def test_registered_forward_structure():
    """Forwards accept inlets, move only fluids and never assign module attributes."""
    for cls in MODULE_REGISTRY.values():
        if "forward" not in cls.__dict__ or not cls.__module__.startswith(("gemini.", "examples.")):
            continue
        try:
            module = cls()
        except (TypeError, ValueError):
            continue
        source, tree = _source_tree(cls.forward)
        _assert_ordered_sections(cls, source, FORWARD_SECTIONS)
        composite = not module.is_leaf
        comments = {comment for comment, _ in _comments(source)}
        assert ("# Modules" in comments) == composite
        assert ("# Outlets" in comments) == bool(module.outlets())
        assert not _self_assignments(tree), f"{cls.__name__}: forward assigns to self"

        arguments = [argument.arg for argument in tree.args.args if argument.arg != "self"]
        assert arguments == list(module.inlets())
        declarations = list(module.inlets().values()) + list(module.outlets().values())
        assert all(
            isinstance(declaration.kind, type) and issubclass(declaration.kind, Stream)
            for declaration in declarations
        )
        _assert_return_block(cls, tree, list(module.outlets()))


def test_leaf_and_composite_output_conventions():
    """Leaves compute plain outputs; composites declare formulas only."""
    for cls in MODULE_REGISTRY.values():
        if not cls.__module__.startswith(("gemini.", "examples.")):
            continue
        try:
            module = cls()
        except (TypeError, ValueError):
            continue
        outputs = list(module.outputs().values())
        if module.is_leaf:
            assert all(output.formula is None for output in outputs)
            if outputs:
                assert type(module)._compute_outputs is not Module._compute_outputs
        else:
            assert all(output.formula is not None for output in outputs)
            assert type(module)._compute_outputs is Module._compute_outputs


def test_method_and_declaration_section_order():
    """Lifecycle methods and declaration sections retain one readable order."""
    for cls in MODULE_REGISTRY.values():
        if not cls.__module__.startswith(("gemini.", "examples.")):
            continue
        methods = [
            name
            for name, value in cls.__dict__.items()
            if inspect.isfunction(value) and name in {"__init__", "forward", "_compute_outputs"}
        ]
        expected = [name for name in ("__init__", "forward", "_compute_outputs") if name in methods]
        assert methods == expected, f"{cls.__name__}: lifecycle method order is {methods}"
        if "__init__" in cls.__dict__:
            source, _ = _source_tree(cls.__dict__["__init__"])
            _assert_ordered_sections(cls, source, INIT_SECTIONS)
