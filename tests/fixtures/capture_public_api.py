"""The frozen public API as data: every name, its parameter names and the schema hashes.

Regenerate with ``PYTHONPATH=. python tests/fixtures/capture_public_api.py`` only together with a
raised ``gm.API_VERSION`` and a line in the change log of ``.claude/docs/api.md``.
"""

import hashlib
import inspect
import json
from pathlib import Path

import gemini as gm

ROOT = Path(__file__).parents[2]
SNAPSHOT = ROOT / "tests" / "fixtures" / "public_api.json"
NAMESPACES = (
    "plants",
    "units",
    "streams",
    "profiles",
    "analysis",
    "economics",
    "checks",
    "testing",
    "optim",
    "runtime",
    "legacy",
)
METHODS = {
    "Module": (
        "describe",
        "parameter_schema",
        "validate_params",
        "help",
        "to_spec",
        "to_dict",
        "from_dict",
        "save",
        "load",
        "set_params",
        "params_at",
        "param_history",
        "bindable",
        "set_bindings",
        "get_module",
        "named_modules",
    ),
    "Plant": ("__init__", "add", "connect", "summary", "validate", "simulate"),
    "Engine": (
        "__init__",
        "simulate",
        "replay",
        "live",
        "save_checkpoint",
        "load_checkpoint",
        "resume",
    ),
    "Results": (
        "names",
        "get",
        "summary",
        "errors",
        "to_frame",
        "to_dict",
        "save",
        "load",
        "to_bytes",
        "from_bytes",
        "energy_report",
    ),
}


def _parameters(function):
    """Return the parameter names of a callable, without ``self`` and ``cls``."""
    names = list(inspect.signature(function).parameters)
    return [name for name in names if name not in ("self", "cls")]


def _member(value):
    """Return the parameters of a function, or the kind of any other public name."""
    if inspect.isclass(value):
        return "class"
    if inspect.ismodule(value):
        return "module"
    return _parameters(value) if callable(value) else type(value).__name__


def _namespace(module):
    return {name: _member(getattr(module, name)) for name in module.__all__}


def _methods(owner, names):
    methods = {}
    for name in names:
        method = getattr(owner, name)
        methods[name] = _parameters(method)
    return methods


def _schemas():
    folder = ROOT / "docs" / "schemas"
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.glob("*.schema.json"))
    }


def capture():
    """Return the snapshot of the public API."""
    errors = {name: getattr(gm.errors, name) for name in gm.errors.__all__}
    classes = {name: value for name, value in errors.items() if isinstance(value, type)}
    return {
        "api_version": gm.API_VERSION,
        "top_level": sorted(gm.__all__),
        "namespaces": {name: _namespace(getattr(gm, name)) for name in NAMESPACES},
        "modules": _namespace(gm.modules),
        "classes": {
            "Module": _methods(gm.modules.Module, METHODS["Module"]),
            "Plant": _methods(gm.Plant, METHODS["Plant"]),
            "Engine": _methods(gm.Engine, METHODS["Engine"]),
            "Results": _methods(gm.Results, METHODS["Results"]),
        },
        "evaluate": _parameters(gm.evaluate),
        "kpi": {"call": _parameters(gm.kpi), "names": gm.kpi.names()},
        "errors": {name: value.code for name, value in classes.items() if hasattr(value, "code")},
        "codes": list(gm.errors.CODES),
        "row_codes": sorted(gm.errors.ROW_CODES),
        "categories": gm.modules.categories(),
        "streams": gm.streams.names(),
        "schemas": _schemas(),
    }


def fingerprint(snapshot):
    """Return the hash of a snapshot, which a test holds per ``API_VERSION``."""
    text = json.dumps(snapshot, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    """Write the snapshot and print its hash for ``SNAPSHOTS`` in the public-API test."""
    snapshot = capture()
    SNAPSHOT.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
    print(fingerprint(snapshot))


if __name__ == "__main__":
    main()
