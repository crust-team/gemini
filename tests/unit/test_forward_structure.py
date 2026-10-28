"""Enforce one source layout for every concrete module forward method."""

import ast
import inspect
import io
import textwrap
import tokenize

from examples.shared.doublet_heat.plant import DoubletHeatPlant  # noqa: F401
from gemini.core.modules.module import MODULE_REGISTRY
from gemini.core.modules.plants import Doublet  # noqa: F401

SECTIONS = ("# Modules", "# Outputs", "# Outlets")


def _source_tree(method):
    source = textwrap.dedent(inspect.getsource(method))
    return source, ast.parse(source).body[0]


def _section_lines(source, cls):
    comments = {
        token.string.strip(): token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT and token.string.strip() in SECTIONS
    }
    mentioned = [section for section in SECTIONS if section in comments]
    ordered = sorted(mentioned, key=comments.get)
    assert mentioned == ordered, f"{cls.__name__}: forward sections are out of order"
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        comment = token.string.strip()
        if any(comment.startswith(section) for section in SECTIONS):
            assert comment in SECTIONS, f"{cls.__name__}: invalid section comment {comment!r}"
    return comments


def _in_section(node, comments, section, end_line):
    start = comments[section]
    stop = min((line for line in comments.values() if line > start), default=end_line + 1)
    return start < node.lineno < stop


def _assigned_self_outputs(tree, output_names):
    assignments = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr in output_names
            ):
                assignments.append((target.attr, node))
    return assignments


def _assigned_locals(tree, comments, section):
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not _in_section(
            node, comments, section, tree.end_lineno
        ):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names.extend(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _assert_module_section(cls, tree, comments):
    if "# Modules" not in comments:
        return
    statements = [
        node for node in tree.body if _in_section(node, comments, "# Modules", tree.end_lineno)
    ]
    assert statements, f"{cls.__name__}: # Modules section is empty"
    assert all(
        any(isinstance(item, ast.Call) for item in ast.walk(node)) for node in statements
    ), f"{cls.__name__}: # Modules may contain only child calls and result unpacking"


def _assert_return_block(cls, tree, outlet_names):
    assert len(tree.body) >= 2, f"{cls.__name__}: forward needs an outlet return block"
    assignment, returned = tree.body[-2:]
    valid_assignment = (
        isinstance(assignment, ast.Assign)
        and len(assignment.targets) == 1
        and isinstance(assignment.targets[0], ast.Name)
        and assignment.targets[0].id == "outlets"
        and isinstance(assignment.value, ast.Call)
        and isinstance(assignment.value.func, ast.Name)
        and assignment.value.func.id == "dict"
        and not assignment.value.args
    )
    assert valid_assignment, f"{cls.__name__}: penultimate statement must be outlets = dict(...)"
    keys = [keyword.arg for keyword in assignment.value.keywords]
    assert keys == outlet_names, f"{cls.__name__}: outlet return order {keys} != {outlet_names}"
    valid_return = (
        isinstance(returned, ast.Return)
        and isinstance(returned.value, ast.Name)
        and returned.value.id == "outlets"
    )
    assert valid_return, f"{cls.__name__}: final statement must be return outlets"


def _child_for_call(module, function):
    parts = []
    while isinstance(function, ast.Attribute):
        parts.append(function.attr)
        function = function.value
    if not isinstance(function, ast.Name) or function.id != "self":
        return None
    current = module
    for part in reversed(parts):
        if part not in current._children:
            return None
        current = current._children[part]
    return current


def test_registered_forward_structure():
    """Concrete forwards use fixed sections, assignments and outlet return blocks."""
    for cls in MODULE_REGISTRY.values():
        if "forward" not in cls.__dict__ or not cls.__module__.startswith(("gemini.", "examples.")):
            continue
        module = cls()
        source, tree = _source_tree(cls.forward)
        comments = _section_lines(source, cls)
        output_names = list(module.outputs())
        outlet_names = list(module.outlets())
        composite = bool(list(module.children()))

        expected_arguments = list(module.inlets())
        actual_arguments = [argument.arg for argument in tree.args.args if argument.arg != "self"]
        assert actual_arguments == expected_arguments, (
            f"{cls.__name__}: forward arguments {actual_arguments} "
            f"!= declared inlets {expected_arguments}"
        )

        assert (
            "# Modules" in comments
        ) == composite, f"{cls.__name__}: # Modules must appear exactly on composites"
        assert ("# Outputs" in comments) == bool(
            output_names
        ), f"{cls.__name__}: # Outputs presence does not match declarations"
        assert ("# Outlets" in comments) == bool(
            outlet_names
        ), f"{cls.__name__}: # Outlets presence does not match declarations"
        _assert_module_section(cls, tree, comments)

        assignments = _assigned_self_outputs(tree, set(output_names))
        assigned_names = {name for name, _ in assignments}
        assert assigned_names == set(
            output_names
        ), f"{cls.__name__}: assigned outputs {sorted(assigned_names)} != {output_names}"
        assert all(
            _in_section(node, comments, "# Outputs", tree.end_lineno) for _, node in assignments
        ), f"{cls.__name__}: output assignment outside # Outputs"

        if outlet_names:
            locals_ = _assigned_locals(tree, comments, "# Outlets")
            unexpected = set(locals_) - set(outlet_names) - {"outlets"}
            assert (
                not unexpected
            ), f"{cls.__name__}: unexpected # Outlets locals {sorted(unexpected)}"
            for name in outlet_names:
                assert (
                    locals_.count(name) == 1
                ), f"{cls.__name__}: outlet {name!r} needs exactly one local in # Outlets"
        _assert_return_block(cls, tree, outlet_names)

        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            child = _child_for_call(module, call.func)
            if child is None:
                continue
            keywords = {keyword.arg for keyword in call.keywords if keyword.arg is not None}
            unexpected = keywords - child.inlets().keys()
            assert not unexpected, (
                f"{cls.__name__}: child {child.path} receives non-inlet keywords "
                f"{sorted(unexpected)}"
            )


def test_stateful_step_sections_are_ordered():
    """Stateful overrides use the same allowed section vocabulary and ordering."""
    for cls in MODULE_REGISTRY.values():
        if not cls.stateful or "step" not in cls.__dict__:
            continue
        source, _ = _source_tree(cls.step)
        comments = _section_lines(source, cls)
        assert "# Modules" not in comments or bool(
            list(cls().children())
        ), f"{cls.__name__}: # Modules is only valid for composites"
