"""The fixed list of stream types that ports carry."""

__all__ = ["names"]

NAMES = (
    "brine",
    "hot_water",
    "chilled_water",
    "gas",
    "electricity",
    "fuel",
    "heat",
    "air",
    "waste",
    "chemical",
)
"""Every port label; ``electricity`` and ``heat`` label ports that carry a ``Power`` value."""


def names():
    """Return the stream types."""
    return list(NAMES)
