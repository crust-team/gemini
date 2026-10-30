"""The plant KPIs under fixed names."""

import pytest

import gemini as gm


def test_kpi_lands_in_this_step():
    """Both names exist."""
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.kpi.names()
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.kpi(None, None)
