"""Enforce fluid-only forwards and leaf/composite output conventions."""

import ast
import inspect
import io
import textwrap
import tokenize

from gemini.core.modules.module import Module
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


def _assert_fixed_signature(cls, name, expected):
    method = getattr(cls, name)
    signature = inspect.signature(method)
    parameters = list(signature.parameters.values())
    actual = [parameter.name for parameter in parameters]
    assert actual == expected, (
        f"{cls.__name__}.{name}: signature must be "
        f"({', '.join(expected)}), got ({', '.join(actual)})"
    )
    for parameter in parameters:
        assert parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ), f"{cls.__name__}.{name}: {parameter.name!r} cannot be variadic or keyword-only"
        assert (
            parameter.default is inspect.Parameter.empty
        ), f"{cls.__name__}.{name}: {parameter.name!r} cannot have a default"


def _port_accesses(tree, variable):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == variable
        ):
            yield node.attr
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == variable
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            yield node.slice.value


def _assert_declared_accesses(cls, method_name, variable, declared):
    _, tree = _source_tree(getattr(cls, method_name))
    for name in _port_accesses(tree, variable):
        assert name in declared, (
            f"{cls.__name__}.{method_name}: unknown {variable[:-1]} {name!r}; "
            f"declared names: {', '.join(declared) or '<none>'}"
        )


def test_fixed_signatures_and_declared_port_accesses(module_classes):
    """Every module lifecycle method receives fixed Ports and reads only declared names."""
    for cls in module_classes:
        _assert_fixed_signature(cls, "forward", ["self", "inlets"])
        _assert_fixed_signature(cls, "_compute_outputs", ["self", "inlets", "outlets"])
        module = cls()
        inlet_names = list(module.inlets())
        outlet_names = list(module.outlets())
        _assert_declared_accesses(cls, "forward", "inlets", inlet_names)
        _assert_declared_accesses(cls, "_compute_outputs", "inlets", inlet_names)
        _assert_declared_accesses(cls, "_compute_outputs", "outlets", outlet_names)


def test_registered_forward_structure(module_classes):
    """Forwards accept inlets, move only fluids and never assign module attributes."""
    for cls in module_classes:
        if "forward" not in cls.__dict__:
            continue
        module = cls()
        source, tree = _source_tree(cls.forward)
        _assert_ordered_sections(cls, source, FORWARD_SECTIONS)
        composite = not module.is_leaf
        comments = {comment for comment, _ in _comments(source)}
        assert ("# Modules" in comments) == composite
        assert ("# Outlets" in comments) == bool(module.outlets())
        assert not _self_assignments(tree), f"{cls.__name__}: forward assigns to self"

        declarations = list(module.inlets().values()) + list(module.outlets().values())
        assert all(
            isinstance(declaration.kind, type) and issubclass(declaration.kind, Stream)
            for declaration in declarations
        )
        _assert_return_block(cls, tree, list(module.outlets()))


def test_leaf_and_composite_output_conventions(module_classes):
    """Leaves compute plain outputs; composites declare formulas only."""
    for cls in module_classes:
        module = cls()
        outputs = list(module.outputs(recurse=False).values())
        if module.is_leaf:
            assert all(output.formula is None for output in outputs)
            if outputs:
                assert type(module)._compute_outputs is not Module._compute_outputs
        else:
            assert all(output.formula is not None for output in outputs)
            assert type(module)._compute_outputs is Module._compute_outputs


def test_method_and_declaration_section_order(module_classes):
    """Lifecycle methods and declaration sections retain one readable order."""
    for cls in module_classes:
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
