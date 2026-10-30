"""The shape every check returns."""

from gemini.utils.jsonable import to_plain


def check(name, passed, value, tolerance, reason=None):
    """Return ``{name, passed, value, tolerance}`` as plain JSON, plus ``reason`` when undecided.

    ``passed`` is ``True`` or ``False``, or ``None`` with the ``reason`` when the results hold
    nothing the check can judge. ``value`` is the measured quantity and ``tolerance`` the limit
    it is judged against, in the unit the check documents.
    """
    result = {"name": name, "passed": passed, "value": value, "tolerance": tolerance}
    if passed is None:
        result["reason"] = reason
    return to_plain(result)
