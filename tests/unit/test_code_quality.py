"""The code-quality bar of ``.claude/docs/conventions.md`` cannot silently drop.

McCabe complexity is checked by flake8 (``max-complexity = 10`` in ``pyproject.toml``).
"""

import ast
import io
import re
import subprocess
import tokenize

import pytest

from tests.fixtures import ROOT

PYTHON_FOLDERS = ("gemini", "examples", "tests", "scripts")
SECTION_HEADERS = {
    "# Modules",
    "# Parameters",
    "# Inlets",
    "# Controls",
    "# Boundaries",
    "# States",
    "# Outputs",
    "# Outlets",
}
TOOL_DIRECTIVE = re.compile(
    r"# (noqa: [A-Z]+\d+(, [A-Z]+\d+)*|type: ignore\[[\w-]+\]|pragma: no cover)"
)
NESTING = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith, ast.Match)
MAX_NESTING = 3
MAX_LINES = 40
LONG_FUNCTIONS = {
    "tests/e2e/test_quickstart.py::test_quickstart": "the literal documented quickstart",
}
FRAMEWORK = re.compile("py" + "tor" + "ch|\\b" + "tor" + "ch\\b", re.IGNORECASE)


def tracked_files():
    """Return the repository's tracked and new, not ignored, files."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return sorted(path for path in set(listed) if (ROOT / path).is_file())


def python_files():
    """Return every Python file in the checked folders."""
    return [
        path for path in tracked_files() if path.endswith(".py") and path.startswith(PYTHON_FOLDERS)
    ]


def functions(path):
    """Yield every function definition of one file."""
    for node in ast.walk(ast.parse((ROOT / path).read_text())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def body_lines(function):
    """Return the number of lines of a function body, excluding its docstring."""
    body = function.body
    if ast.get_docstring(function) is not None:
        body = body[1:]
    return body[-1].end_lineno - body[0].lineno + 1 if body else 0


def nesting(node, depth=0):
    """Return the deepest block nesting inside a node; an ``elif`` chain counts once."""
    deepest = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        is_elif = isinstance(node, ast.If) and node.orelse == [child] and isinstance(child, ast.If)
        nested = isinstance(child, NESTING) and not is_elif
        deepest = max(deepest, nesting(child, depth + 1 if nested else depth))
    return deepest


def test_only_section_headers_and_tool_directives_are_comments():
    """Explanations live in docstrings, never in comments inside code."""
    found = []
    for path in python_files():
        source = io.StringIO((ROOT / path).read_text())
        for token in tokenize.generate_tokens(source.readline):
            text = token.string.strip()
            is_allowed = text in SECTION_HEADERS or TOOL_DIRECTIVE.fullmatch(text)
            if token.type == tokenize.COMMENT and not is_allowed:
                found.append(f"{path}:{token.start[0]}: {text}")
    assert found == []


def test_functions_nest_at_most_three_blocks():
    """Guard clauses keep every function at most three blocks deep."""
    deep = [
        f"{path}:{function.lineno} {function.name} ({nesting(function)})"
        for path in python_files()
        for function in functions(path)
        if nesting(function) > MAX_NESTING
    ]
    assert deep == []


def test_functions_are_short_or_documented_exceptions():
    """Functions stay within about 40 lines; each longer one is listed with its reason."""
    long = {
        f"{path}::{function.name}"
        for path in python_files()
        for function in functions(path)
        if body_lines(function) > MAX_LINES
    }
    assert long == set(LONG_FUNCTIONS)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f():\n    if a:\n        for b in c:\n            pass\n", 2),
        ("def f():\n    if a:\n        pass\n    elif b:\n        pass\n", 1),
    ],
)
def test_nesting_counts_blocks_but_not_elif_chains(source, expected):
    """The nesting measure ignores ``elif`` chains."""
    assert nesting(ast.parse(source).body[0]) == expected


def test_no_framework_names_in_tracked_text_files():
    """Concepts are described directly, without naming the framework the design resembles."""
    found = []
    for path in tracked_files():
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        found.extend(
            f"{path}:{number}"
            for number, line in enumerate(text.splitlines(), 1)
            if FRAMEWORK.search(line)
        )
    assert found == []
