"""The plant file, format 2: the sections every module tree shares, read and written.

A file holds ``format``, ``name``, ``modules``, ``connections`` and, keyed by dotted path from the
root (``""`` is the root), ``fluids``, ``boundary``, ``bindings`` and ``param_history``. A
handwritten root writes its class as ``type`` and every parameter of its tree as flat dotted
``params``. A stated value stays as written while it still equals the current one.
"""

from contextlib import contextmanager

from pydantic import ValidationError as PydanticError
from pydantic_core import to_jsonable_python

from gemini.backends import runtime
from gemini.errors import (
    GeminiError,
    PlantFormatError,
    UnknownNameError,
    ValidationError,
)
from gemini.modules import design
from gemini.types.bindings import DatedParams, ModuleBindings
from gemini.types.fluid import Fluid
from gemini.utils.jsonable import to_plain
from gemini.utils.strings import close_matches, did_you_mean

FORMAT = 2
SECTIONS = ("fluids", "boundary", "bindings", "param_history")


class Report:
    """Collect the problems of reading a spec, or raise the first one when ``strict``."""

    def __init__(self, strict=False):
        """Start without problems."""
        self.strict = strict
        self.items = []
        self.broken = set()

    def skips(self, text):
        """Return whether ``text`` names a module that failed to build, whose problem is known."""
        return any(text == path or text.startswith(path + ".") for path in self.broken)

    @contextmanager
    def guard(self, path):
        """Turn a ``GeminiError`` raised inside the block into a problem at ``path``."""
        try:
            yield
        except GeminiError as error:
            if self.strict:
                raise
            self.items.append(problem(path, error))


def problem(path, error):
    """Return ``{path, message, code, suggestions}`` for an error raised at spec ``path``."""
    inner = getattr(error, "path", None)
    full = f"{path}.{inner}" if path and inner else path or inner or ""
    return {
        "path": full,
        "message": str(error),
        "code": error.code,
        "suggestions": list(error.suggestions),
    }


def format_error(data):
    """Return the ``PlantFormatError`` for data that is not format 2, else ``None``."""
    if not isinstance(data, dict):
        return PlantFormatError(f"plant file = {type(data).__name__}; expected a mapping")
    if data.get("format") == FORMAT:
        return None
    if "version" in data:
        return PlantFormatError(
            f"plant file version = {data['version']!r}; expected format {FORMAT}: "
            "convert it with gm.plants.migrate",
            code="old_format",
            path="version",
        )
    return PlantFormatError(
        f"plant file format = {data.get('format')!r}; expected {FORMAT}", path="format"
    )


def plain_value(value):
    """Return a parameter value as plain JSON."""
    return to_plain(to_jsonable_python(value))


def tree_params(module):
    """Return every initialized parameter of the tree as ``{dotted path: plain value}``."""
    return {
        path: plain_value(parameter.value)
        for path, parameter in module.named_parameters()
        if parameter.initialized
    }


def keep_stated(stated, current, parse):
    """Return ``stated`` while it parses to ``current``, else ``None``."""
    try:
        return stated if stated is not None and parse(stated) == current else None
    except (PydanticError, ValueError, TypeError, GeminiError):
        return None


def _fluids(root, stated, baselines):
    default = runtime.get_default_fluid()
    result = {}
    for path, module in root.named_modules():
        current = module._fluid
        kept = keep_stated(stated.get(path), current, Fluid.model_validate)
        if kept is not None:
            result[path] = kept
        elif path in stated or current != baselines.get(path, default):
            result[path] = current.model_dump(mode="json")
    return result


def _boundary(root):
    return {
        path: to_plain(module.boundary) for path, module in root.named_modules() if module.boundary
    }


def _bindings(root, stated):
    result = {}
    for path, current in root.bindings.items():
        kept = keep_stated(stated.get(path), current, ModuleBindings.model_validate)
        result[path] = kept if kept is not None else current.model_dump(mode="json")
    return result


def _parse_history(entries):
    return [DatedParams.model_validate(item) for item in entries]


def _history(root, stated):
    result = {}
    for path, module in root.named_modules():
        current = module._param_history
        if len(current) == 1 and current[0].valid_from is None:
            continue
        kept = keep_stated(stated.get(path), current, _parse_history)
        result[path] = kept if kept is not None else [i.model_dump(mode="json") for i in current]
    return to_plain(result)


def write_sections(root, stated=None, baselines=None):
    """Return the ``fluids``, ``boundary``, ``bindings`` and ``param_history`` of a tree.

    ``stated`` holds the sections of the spec the tree was read from and ``baselines`` the
    fluid each path had when it was created; empty sections other than ``bindings`` and
    ``param_history`` are left out.
    """
    stated = stated or {}
    sections = {
        "fluids": _fluids(root, stated.get("fluids", {}), baselines or {}),
        "boundary": _boundary(root),
        "bindings": _bindings(root, stated.get("bindings", {})),
        "param_history": _history(root, stated.get("param_history", {})),
    }
    return {
        key: value
        for key, value in sections.items()
        if value or key in ("bindings", "param_history")
    }


def _module_at(root, path):
    modules = dict(root.named_modules())
    if path not in modules:
        raise UnknownNameError(
            f"{root.path}: unknown module path {path!r}{did_you_mean(path, modules)}",
            suggestions=close_matches(path, modules),
        )
    return modules[path]


def _read_fluid(module, value):
    try:
        object.__setattr__(module, "_fluid", Fluid.model_validate(value))
    except PydanticError as error:
        raise ValidationError(f"fluid: {error}", code="invalid_value") from error


def _read_boundary(module, value):
    if not isinstance(value, dict):
        raise ValidationError("boundary: expected a mapping", code="invalid_format")
    module.boundary = dict(value)


def _read_history(module, entries):
    if not isinstance(entries, list):
        raise ValidationError("param_history: expected a list", code="invalid_format")
    snapshots = []
    for index, item in enumerate(entries):
        try:
            snapshot = DatedParams.model_validate(item)
        except PydanticError as error:
            raise ValidationError(f"[{index}]: {error}", path=f"[{index}]") from error
        for name, value in snapshot.params.items():
            design.parameter(module, name).validate(value)
        snapshots.append(snapshot)
    module._param_history = snapshots


def _read_bindings(root, path, value):
    design.set_bindings(root, path, value)


def read_sections(root, spec, report):
    """Apply the sections of ``spec`` to the tree, adding each problem to ``report``."""
    readers = {
        "fluids": lambda path, value: _read_fluid(_module_at(root, path), value),
        "boundary": lambda path, value: _read_boundary(_module_at(root, path), value),
        "param_history": lambda path, value: _read_history(_module_at(root, path), value),
        "bindings": lambda path, value: _read_bindings(root, path, value),
    }
    for section, read in readers.items():
        for path, value in spec.get(section, {}).items():
            if report.skips(path):
                continue
            with report.guard(f"{section}.{path}"):
                read(path, value)


def read_params(root, params, report, prefix="params"):
    """Set flat dotted ``params`` on the tree as undated design values."""
    for name, value in params.items():
        with report.guard(f"{prefix}.{name}"):
            design.set_params(root, "", {name: value})


def module_spec(module):
    """Return the format 2 spec of a handwritten module tree."""
    kind = type(module).__name__
    spec = {"format": FORMAT, "name": kind, "type": kind, "modules": {}, "connections": []}
    spec["params"] = tree_params(module)
    return spec | write_sections(module)


def module_from_spec(cls, spec):
    """Build ``cls()`` and fill it from a format 2 spec; raise on the first problem."""
    error = format_error(spec)
    if error is not None:
        raise error
    report = Report(strict=True)
    root = cls()
    read_params(root, spec.get("params", {}), report)
    read_sections(root, spec, report)
    return root
