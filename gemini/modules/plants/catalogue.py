"""The plant catalogue: which plants exist and how to get one."""

from gemini.errors import NotImplementedYet, ValidationError
from gemini.modules._utils import registry
from gemini.modules.plants import library, templating
from gemini.modules.plants.spec import from_spec
from gemini.utils.files import read_json
from gemini.utils.strings import close_matches, did_you_mean, join_names

EXAMPLES = library.SPECS / "examples"


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

    ``Doublet`` and ``DoubletHeatPlant`` carry the values of ``datasets/doublet_heat``
    (``plants/specs/examples/``); the other plants carry the values their unit tests use, the
    design parameters only: controls and boundaries are inputs of a run. A registered plant
    without sourced values raises ``NotImplementedYet`` naming it.
    """
    _check("example", name)
    path = EXAMPLES / f"{name}.json"
    if not path.exists():
        raise NotImplementedYet(f"plants.example: {name!r} has no sourced parameter values yet")
    return from_spec(read_json(path))


def templates():
    """Return ``[{name, title, description, purpose}]`` of every template.

    ``purpose`` is ``heating``, ``cooling`` or ``both``. ``from_template(name, parameters)``
    fills one.
    """
    return templating.listing()
