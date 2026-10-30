"""The shape every economics function returns."""

from gemini.utils.jsonable import to_plain


def outcome(value, unit, reason=None, **details):
    """Return ``{value, unit, reason, ...}`` as plain JSON.

    ``value`` is a number in ``unit``, or ``None`` with the ``reason`` text when the inputs
    cannot give it; ``details`` adds the named inputs and parts of the result.
    """
    return to_plain({"value": value, "unit": unit, "reason": reason, **details})
