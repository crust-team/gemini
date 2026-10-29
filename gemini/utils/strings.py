"""Names, dotted paths and pieces of error messages."""

import re
from difflib import get_close_matches

_WORD_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z][a-z])|(?<=[a-z0-9])(?=[A-Z])")


def snake_case(name):
    """Return a CamelCase name in snake_case, keeping acronyms together (``ESP`` → ``esp``)."""
    return _WORD_BOUNDARY.sub("_", name).lower()


def first_paragraph(text):
    """Return the first paragraph of a docstring as one line."""
    return text.split("\n\n", 1)[0].replace("\n", " ")


def join_path(prefix, name):
    """Join a dotted parent path and a name; an empty prefix denotes the root."""
    return f"{prefix}.{name}" if prefix else name


def split_path(path):
    """Split a dotted path into its parent path and final name."""
    parent, _, name = path.rpartition(".")
    return parent, name


def join_names(names):
    """Return names as a comma-separated list, or ``<none>`` when there are none."""
    return ", ".join(names) or "<none>"


def did_you_mean(name, candidates):
    """Return ``"; did you mean 'x'?"`` for the closest candidate, or an empty string."""
    matches = get_close_matches(str(name), list(candidates), n=1)
    return f"; did you mean {matches[0]!r}?" if matches else ""
