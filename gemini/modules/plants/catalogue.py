"""The plant catalogue: which plants exist and how to get one."""

from gemini.errors import NotImplementedYet, ValidationError
from gemini.modules._utils import registry
from gemini.modules._utils.serialization import SECTIONS, Report, read_sections
from gemini.modules.plant import Plant
from gemini.modules.plants import templating
from gemini.utils import paths
from gemini.utils.files import read_json
from gemini.utils.strings import close_matches, did_you_mean, join_names


def names():
    """Return the registry names of the plants, sorted: the spec plants and the special cases."""
    return registry.names("plants")


def _check(function, name):
    valid = names()
    if name not in valid:
        raise ValidationError(
            f"plants.{function}: unknown plant {name!r}; valid: {join_names(valid)}"
            f"{did_you_mean(name, valid)}",
            path=name,
            suggestions=close_matches(name, valid),
            code="unknown_name",
        )


def get(name):
    """Return a new plant of registry name ``name`` whose parameters are not set.

    A spec plant comes back as a ``Plant`` and a special case as an instance of its class. An
    unknown name, or the name of a module that is not a plant, raises ``ValidationError`` with
    close matches in ``suggestions``.
    """
    _check("get", name)
    found = registry.get(name)
    return found() if isinstance(found, type) else found


def example(name):
    """Return a new plant ``name`` with real parameter values.

    The plant comes from ``get``; ``inputs/plants/<name>.json`` of a source checkout gives its
    ``params`` and any ``fluids``, ``boundary``, ``bindings`` and ``param_history``, under the keys
    of a plant file. ``Doublet`` and ``DoubletHeatPlant`` carry the values of the measured doublet;
    the other plants carry the values their unit tests use, the design parameters only: controls
    and boundaries are inputs of a run. A registered plant without a file raises
    ``NotImplementedYet`` naming it, and without ``inputs/`` this raises ``inputs_missing``.
    """
    _check("example", name)
    path = paths.plant_values(name)
    if not path.exists():
        raise NotImplementedYet(f"plants.example: {name!r} has no sourced parameter values yet")
    plant, values = get(name), read_json(path)
    plant.set_params("", values["params"])
    read_sections(plant, values, Report(strict=True))
    if isinstance(plant, Plant):
        plant._sections = {key: values.get(key, {}) for key in SECTIONS}
    return plant


def templates():
    """Return ``[{name, title, description, purpose}]`` of every template.

    ``purpose`` is ``heating``, ``cooling`` or ``both``. ``from_template(name, parameters)``
    fills one.
    """
    return templating.listing()
