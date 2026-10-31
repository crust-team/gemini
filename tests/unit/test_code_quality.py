"""The code-quality bar of ``.claude/docs/conventions.md`` cannot silently drop.

McCabe complexity is checked by flake8 (``max-complexity = 10`` in ``pyproject.toml``).
"""

import ast
import functools
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
    "tests/e2e/test_quickstart.py::test_quickstart": "one end-to-end quickstart path",
}
EARLY_EXITS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
BUILTIN_ERRORS = {"ValueError", "TypeError", "KeyError", "RuntimeError"}
RAISED_CLASSES = {
    "ValidationError",
    "DefinitionError",
    "PhysicsError",
    "RunError",
    "Cancelled",
    "NotImplementedYet",
    "GeminiError",
    "TraceError",
    "UnknownKey",
    "UnknownPort",
    "UnknownMember",
    "AttributeError",
    "NotImplementedError",
    "KeyError",
    "TypeError",
    "ValueError",
    "RuntimeError",
}
"""What the package raises; the built-ins are for the exempt topics of ``gemini.utils``."""
VALIDATORS = {"model_validator", "field_validator"}
FRAMEWORK = re.compile("py" + "tor" + "ch|\\b" + "tor" + "ch\\b", re.IGNORECASE)
FRAMEWORK_STEM = "tor" + "ch"
"""Lowercase text that every ``FRAMEWORK`` match contains, checked before the slower regex."""
MATH_OPS = {
    "exp",
    "expm1",
    "log",
    "log10",
    "log1p",
    "sqrt",
    "power",
    "pow",
    "sin",
    "cos",
    "tan",
    "atan",
}
ARITHMETIC = (ast.Pow, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)
FORMULA_EXCEPTIONS = {
    "gemini/modules/exchangers/heatexchanger.py: np.any": "health decides on scalars and arrays; "
    "ops has no reduction to a Python bool",
    "gemini/modules/module.py: literal 4": "how many parameters repr shows, not physics",
    "gemini/modules/module.py: np.float64": "the eager scope wraps a recorded float, not maths",
    "gemini/modules/module.py: np.ndarray": "a type test of the array path, not maths",
    "gemini/modules/pumps/esp.py: np.asarray": "the float32 cast of the retained precision",
    "gemini/modules/pumps/esp.py: np.float32": "the float32 cast of the retained precision",
    "gemini/modules/_utils/serialization.py: literal 2": "the plant file format number",
}
"""``file: marker`` of what a module may keep, each with its reason; see ``formula_markers``."""
SAME_FORM = {
    (
        "chemistry.py::co2_solubility_gas",
        "control/_physics.py::pid_derivative",
        "hydraulics.py::reynolds_number",
    ): "a product over a divisor: dissolved CO2, a PID term and the Reynolds number",
    (
        "hydraulics.py::productivity_pressure",
        "pumps/_physics.py::heat_rejected",
    ): "a less b over c: "
    "compressor heat and a linear inflow relation",
    (
        "ground.py::stored_heat",
        "pumps/_physics.py::line_shaft_friction_power",
        "storage/_physics.py::ice_stored_cold",
    ): "a product of three: stored heat, shaft friction and latent cold",
    (
        "dispatch.py::circuit_flow",
        "pumps.py::best_efficiency_ratio",
        "refrigeration.py::cooling_minimum_sink_rate",
    ): "a over a "
    "product: a pump load ratio and a heat pump's smallest sink capacity rate",
}
"""Physics functions with one normalised body that are different relations, each with its reason."""


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


@functools.cache
def functions(path):
    """Return every function definition of one file, parsed once per process."""
    tree = ast.parse((ROOT / path).read_text())
    return tuple(
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


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


PYTHON_FILES = python_files()
LAYERED_UTILS = ("gemini/utils/data/", "gemini/utils/legacy/")
PACKAGE_FILES = [
    path
    for path in PYTHON_FILES
    if path.startswith("gemini/")
    and (not path.startswith("gemini/utils/") or path.startswith(LAYERED_UTILS))
]


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_only_section_headers_and_tool_directives_are_comments(path):
    """Explanations live in docstrings, never in comments inside code."""
    found = []
    source = io.StringIO((ROOT / path).read_text())
    for token in tokenize.generate_tokens(source.readline):
        text = token.string.strip()
        is_allowed = text in SECTION_HEADERS or TOOL_DIRECTIVE.fullmatch(text)
        if token.type == tokenize.COMMENT and not is_allowed:
            found.append(f"{path}:{token.start[0]}: {text}")
    assert found == []


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_functions_nest_at_most_three_blocks(path):
    """Guard clauses keep every function at most three blocks deep."""
    deep = [
        f"{path}:{function.lineno} {function.name} ({nesting(function)})"
        for function in functions(path)
        if nesting(function) > MAX_NESTING
    ]
    assert deep == []


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_functions_are_short_or_documented_exceptions(path):
    """Functions stay within about 40 lines; each longer one is listed with its reason."""
    long = {
        f"{path}::{function.name}"
        for function in functions(path)
        if body_lines(function) > MAX_LINES
    }
    assert long == {name for name in LONG_FUNCTIONS if name.startswith(f"{path}::")}


def test_long_function_exceptions_exist():
    """Every listed long-function exception names an existing function."""
    listed_paths = {name.partition("::")[0] for name in LONG_FUNCTIONS}
    names = {
        f"{path}::{function.name}"
        for path in PYTHON_FILES
        if path in listed_paths
        for function in functions(path)
    }
    assert set(LONG_FUNCTIONS) <= names


@pytest.mark.parametrize("path", PYTHON_FILES)
def test_no_else_after_an_early_exit(path):
    """A block that ends in ``return``, ``raise``, ``continue`` or ``break`` has no ``else``."""
    found = [
        f"{path}:{node.lineno}"
        for node in ast.walk(ast.parse((ROOT / path).read_text()))
        if isinstance(node, ast.If) and node.orelse and isinstance(node.body[-1], EARLY_EXITS)
    ]
    assert found == []


def raised_name(node):
    """Return the class name a ``raise`` statement raises, or None."""
    exception = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
    return exception.id if isinstance(exception, ast.Name) else None


def is_validator(function):
    """Tell whether a function is a validator, which must raise ``ValueError``."""
    return any(
        isinstance(decorator, ast.Call) and getattr(decorator.func, "id", None) in VALIDATORS
        for decorator in function.decorator_list
    )


@pytest.mark.parametrize("path", PACKAGE_FILES)
def test_package_code_raises_gemini_errors(path):
    """Deliberate errors use ``gm.errors``; ``gemini.utils`` topics and validators are exempt."""
    found = [
        f"{path}:{node.lineno} {raised_name(node)}"
        for function in functions(path)
        if not is_validator(function)
        for node in ast.walk(function)
        if isinstance(node, ast.Raise) and node.exc and raised_name(node) in BUILTIN_ERRORS
    ]
    assert found == []


@pytest.mark.parametrize("path", PACKAGE_FILES)
def test_package_code_raises_only_the_allowed_classes(path):
    """A raise names a public class of ``gm.errors``, a private lookup or a Python protocol error.

    ``TraceError`` is internal to ``gemini/graph/``; a former class has no way back in.
    """
    found = [
        f"{path}:{node.lineno} {raised_name(node)}"
        for function in functions(path)
        for node in ast.walk(function)
        if isinstance(node, ast.Raise) and node.exc and _named_class(raised_name(node))
        if raised_name(node) not in RAISED_CLASSES
    ]
    assert found == []
    if not str(path).startswith("gemini/graph/"):
        assert "TraceError" not in {raised_name(node) for node in _raises(path)}


def _raises(path):
    return [
        node
        for function in functions(path)
        for node in ast.walk(function)
        if isinstance(node, ast.Raise) and node.exc
    ]


def _named_class(name):
    return bool(name) and name[0].isupper()


def formula_markers(source):
    """Return the marks of a formula in a module's source, each once with its line."""
    found = {}
    for node in ast.walk(ast.parse(source)):
        marker = None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ARITHMETIC):
            marker = type(node.op).__name__
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            owner, name = node.value.id, node.attr
            if owner in ("math", "np", "numpy") or (owner == "ops" and name in MATH_OPS):
                marker = f"{owner}.{name}"
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
            marker = None if node.value in (0, 1) else f"literal {node.value}"
        if marker:
            found.setdefault(marker, node.lineno)
    return found


MODULE_FILES = [
    path
    for path in PACKAGE_FILES
    if path.startswith("gemini/modules/")
    and not path.startswith("gemini/modules/plants/")
    and not path.endswith("/_physics.py")
]
PHYSICS_FILES = [
    path
    for path in PACKAGE_FILES
    if path.startswith("gemini/physics/") or path.endswith("/_physics.py")
]
CATEGORY_PHYSICS = [path for path in PHYSICS_FILES if path.startswith("gemini/modules/")]
PHYSICS_IMPORTS = ("gemini.errors", "gemini.ops", "gemini.physics", "gemini.types")


@pytest.mark.parametrize("path", MODULE_FILES)
def test_modules_hold_no_formulas(path):
    """Physics lives in ``gemini/physics/`` or a ``_physics.py``: a module declares and wires."""
    markers = formula_markers((ROOT / path).read_text())
    found = {f"{path}: {marker}": line for marker, line in markers.items()}
    assert {name: line for name, line in found.items() if name not in FORMULA_EXCEPTIONS} == {}


def test_formula_exceptions_exist():
    """Every listed exception still names something the scan finds."""
    for name in FORMULA_EXCEPTIONS:
        path, _, marker = name.partition(": ")
        assert marker in formula_markers((ROOT / path).read_text())


class _Names(ast.NodeTransformer):
    """Replace argument and local names by their order of appearance."""

    def __init__(self):
        self.names = {}

    def visit_Name(self, node):
        """Rename a local or an argument; leave modules, functions and constants alone."""
        if isinstance(node.ctx, ast.Store) or node.id in self.names:
            node.id = self.names.setdefault(node.id, f"name{len(self.names)}")
        return node


def normalised_body(function):
    """Return the body of a function without docstring, annotations and its own names."""
    names = _Names()
    for argument in function.args.posonlyargs + function.args.args + function.args.kwonlyargs:
        names.names[argument.arg] = f"name{len(names.names)}"
    body = function.body[1:] if ast.get_docstring(function) else function.body
    return "".join(ast.dump(names.visit(statement)) for statement in body)


def is_one_operation(function):
    """Tell whether a body is one operator on two names: a definition, not a formula."""
    body = function.body[1:] if ast.get_docstring(function) else function.body
    value = body[0].value if len(body) == 1 and isinstance(body[0], ast.Return) else None
    operands = (getattr(value, "left", None), getattr(value, "right", None))
    return isinstance(value, ast.BinOp) and all(isinstance(item, ast.Name) for item in operands)


def physics_copies():
    """Return groups of public and private physics functions with one normalised body."""
    bodies = {}
    for path in PHYSICS_FILES:
        for function in ast.parse((ROOT / path).read_text()).body:
            if isinstance(function, ast.FunctionDef) and not is_one_operation(function):
                short = path.removeprefix("gemini/physics/").removeprefix("gemini/modules/")
                name = f"{short}::{function.name}"
                bodies.setdefault(normalised_body(function), []).append(name)
    return [tuple(sorted(names)) for names in bodies.values() if len(names) > 1]


def gemini_imports(path):
    """Return the absolute ``gemini`` packages one file imports, ``gemini.ops`` for ``ops``."""
    found = set()
    for node in ast.walk(ast.parse((ROOT / path).read_text())):
        if isinstance(node, ast.ImportFrom) and node.module == "gemini":
            found |= {f"gemini.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("gemini."):
            found.add(node.module)
    return found


@pytest.mark.parametrize("path", CATEGORY_PHYSICS)
def test_category_physics_imports_only_the_shared_layers(path):
    """A ``_physics.py`` reads the shared physics, never another category's ``_physics.py``."""
    outside = [
        name
        for name in gemini_imports(path)
        if not any(name == allowed or name.startswith(f"{allowed}.") for allowed in PHYSICS_IMPORTS)
    ]
    assert outside == []


@pytest.mark.parametrize("path", CATEGORY_PHYSICS)
def test_category_physics_serves_its_own_category(path):
    """A function a second category needs moves up into ``gemini/physics/``."""
    category = path.split("/")[2]
    users = [
        other
        for other in PACKAGE_FILES
        if f"gemini.modules.{category}" in (ROOT / other).read_text()
        and "_physics" in (ROOT / other).read_text()
        and not other.startswith((f"gemini/modules/{category}/", "gemini/modules/_utils/"))
    ]
    assert users == []


def test_no_two_physics_functions_share_a_body():
    """Every formula exists once; a copy with renamed arguments counts as a copy."""
    assert set(physics_copies()) == set(SAME_FORM)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x = a * 2", {"Mult": 1, "literal 2": 1}),
        ("x = ops.exp(a)", {"ops.exp": 1}),
        ("x = ops.where(a, 0, 1)", {}),
        ("x = math.pi", {"math.pi": 1}),
        ("x = np.sum(a)", {"np.sum": 1}),
    ],
)
def test_formula_markers_find_a_formula(source, expected):
    """The scan sees arithmetic, maths calls and numbers other than 0 and 1."""
    assert formula_markers(source) == expected


def test_a_copy_with_other_argument_names_has_the_same_body():
    """The normalised body ignores docstrings and argument names, not the formula."""
    first, second, third = ast.parse(
        'def f(a, b):\n    """Doc."""\n    return a * b + 1\n'
        "def g(x, y):\n    return x * y + 1\n"
        "def h(x, y):\n    return x * y + 2\n"
    ).body
    assert normalised_body(first) == normalised_body(second) != normalised_body(third)


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
    """Concepts are described directly, without naming the framework the design resembles.

    Only files containing ``FRAMEWORK_STEM`` are searched line by line: every match contains it,
    so the result is the same, and the case-insensitive regex over the 17 MB of example CSVs no
    longer pushes the test past the one-second budget on CI runners.
    """
    found = []
    for path in tracked_files():
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if FRAMEWORK_STEM not in text.lower():
            continue
        found.extend(
            f"{path}:{number}"
            for number, line in enumerate(text.splitlines(), 1)
            if FRAMEWORK.search(line)
        )
    assert found == []
