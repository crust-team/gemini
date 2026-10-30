"""The plant KPIs under fixed names."""

from gemini.errors import NotImplementedYet


def names():
    """Return the fixed KPI names."""
    raise NotImplementedYet("kpi.names")


def kpi(plant, results):
    """Return every KPI of a finished run by its fixed name."""
    raise NotImplementedYet("kpi")


kpi.names = names
