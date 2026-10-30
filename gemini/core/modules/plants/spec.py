"""The plant spec as data: read it, check it, and the plant file is the same document."""

from gemini.core.modules.plants import reader
from gemini.core.modules.plants.builder import Plant


def from_spec(spec):
    """Build a plant from a format 2 spec; one ``ValidationError`` lists every problem."""
    return reader.read(Plant, spec)


def validate(spec):
    """Return every problem of ``spec`` as ``[{path, message, code, suggestions}]``; never raises.

    ``path`` points into the spec, for example ``connections[1].target``.
    """
    return reader.problems(Plant, spec)


from_dict = from_spec
