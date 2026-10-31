"""The plant spec as data: read it, check it, and the plant file is the same document."""

from gemini.errors.base import reported
from gemini.modules.plants import reader
from gemini.modules.plants.builder import Plant


def from_spec(spec):
    """Build a plant from a format 2 spec; one ``ValidationError`` lists every problem."""
    return reader.read(Plant, spec)


def validate(spec, on_error="raise"):
    """Check ``spec`` and return ``[]``, or raise one ``ValidationError`` with every problem.

    With ``on_error="record"`` nothing is raised and the problems are returned, each
    ``{path, code, message, suggestions}``: the list the error carries in ``problems``. ``path``
    points into the spec, for example ``connections[1].target``.
    """
    return reported(reader.problems(Plant, spec) + reader.root_problems(spec), on_error)


from_dict = from_spec
