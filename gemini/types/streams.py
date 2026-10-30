"""The fixed list of stream types that ports carry."""

__all__ = ["names"]

NAMES = ("brine", "hot_water", "chilled_water", "gas", "electricity", "fuel")
"""Every stream type; ``electricity`` and ``fuel`` name connections of the flowsheet only."""


def names():
    """Return the stream types."""
    return list(NAMES)
