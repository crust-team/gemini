"""Convert a format 1 plant file (class paths, one entry per module) to a format 2 spec."""

from copy import deepcopy

from gemini.backends import runtime
from gemini.errors import GeminiError, PlantFormatError
from gemini.modules.plants import library, reader
from gemini.modules.plants.builder import Plant
from gemini.modules.serialization import FORMAT, SECTIONS, plain_value
from gemini.types.fluid import Fluid
from gemini.utils.strings import join_path


def _failed(message, path=None):
    return PlantFormatError(message, code="migration_failed", path=path)


def _place(spec, path, params):
    """Put the params of the old module at ``path`` into the spec entry that holds it."""
    if not params:
        return
    parts = path.split(".")
    modules = spec["modules"]
    for index, part in enumerate(parts):
        if part not in modules:
            raise _failed(f"module {path!r} is not in the plant's wiring", path=path)
        entry = modules[part]
        if "modules" not in entry:
            prefix = ".".join(parts[index + 1 :])
            target = entry.setdefault("params", {})
            target.update({join_path(prefix, name): value for name, value in params.items()})
            return
        modules = entry["modules"]
    if params:
        raise _failed(f"module {path!r} is a group but has parameters", path=path)


def _sections(entries):
    default = runtime.get_default_fluid()
    sections = {"fluids": {}, "boundary": {}, "bindings": {}, "param_history": {}}
    for path, entry in entries.items():
        if "fluid" in entry and Fluid.model_validate(entry["fluid"]) != default:
            sections["fluids"][path] = entry["fluid"]
        if entry.get("boundary"):
            sections["boundary"][path] = deepcopy(entry["boundary"])
        for key, value in entry.get("bindings", {}).items():
            sections["bindings"][join_path(path, key)] = deepcopy(value)
        history = entry.get("param_history", [])
        if len(history) != 1 or history[0].get("valid_from") is not None:
            sections["param_history"][path] = deepcopy(history)
    return {
        key: value
        for key, value in sections.items()
        if value or key in ("bindings", "param_history")
    }


def _changed(plant, path, params):
    """Return the stored params that differ from the starting value of the shipped plant."""
    module = plant._find_submodule(path)
    if module is None:
        raise _failed(f"module {path!r} is not in the plant's wiring", path=path)
    declarations = dict(module.named_parameters())
    return {
        name: value
        for name, value in params.items()
        if name not in declarations
        or not declarations[name].initialized
        or plain_value(declarations[name].value) != value
    }


def _structured(name, entries):
    spec = library.shipped(name)
    plant = library.build(name)
    for path, entry in entries.items():
        if path:
            _place(spec, path, _changed(plant, path, entry.get("params", {})))
    kept = {key: value for key, value in spec.items() if key not in SECTIONS}
    return kept | _sections(entries)


def _handwritten(name, entries):
    params = {
        join_path(path, key): value
        for path, entry in entries.items()
        for key, value in entry.get("params", {}).items()
    }
    spec = {"format": FORMAT, "name": name, "type": name, "modules": {}, "connections": []}
    return spec | {"params": params} | _sections(entries)


def _convert(old):
    if not isinstance(old, dict) or old.get("version") != 1:
        raise _failed(
            f"version = {old.get('version') if isinstance(old, dict) else old!r}; expected 1"
        )
    name = old["plant_type"].split(":")[-1].split(".")[-1]
    entries = old["modules"]
    if library.has(name):
        spec = _structured(name, entries)
        problems = reader.problems(Plant, spec)
        if problems:
            raise _failed(
                f"{problems[0]['path']}: {problems[0]['message']}", path=problems[0]["path"]
            )
        return spec
    return _handwritten(name, entries)


def migrate(old):
    """Convert a format 1 plant file to a format 2 spec; a spec is returned as a copy.

    A tree whose root class is a shipped plant takes that plant's wiring, with the stored
    values filled in; any other root is written as a handwritten root with flat dotted params.
    Failures raise ``PlantFormatError`` with code ``migration_failed``.
    """
    if isinstance(old, dict) and old.get("format") == FORMAT:
        return deepcopy(old)
    try:
        return _convert(old)
    except GeminiError:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise _failed(f"plant file: {type(error).__name__}: {error}") from error
