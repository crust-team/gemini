"""Cost aggregation never silently mixes valuation bases."""

import pytest

from gemini.core.modules.container import Sequential
from gemini.core.modules.treatment.filter import Filter
from gemini.core.types.cost import Cost


class CostedFilter(Filter):
    """Fictional cost for testing aggregation, not an equipment estimate."""

    def capex(self):
        """Return a sourced fixture estimate."""
        return self.estimate


def test_cost_aggregation():
    """Costs sum all components only when currency and year match."""
    first, second = CostedFilter(), CostedFilter()
    first.estimate = Cost(
        capex=100, opex_fixed=10, opex_variable=0.001, price_year=2024, source="test fixture"
    )
    second.estimate = first.estimate
    plant = Sequential(first, second)
    assert plant.cost().capex == 200
    assert plant.cost().opex_fixed == 20
    assert plant.cost().opex_variable == 0.002
    for change in ({"currency": "USD"}, {"price_year": 2025}):
        second.estimate = first.estimate.model_copy(update=change)
        with pytest.raises(ValueError, match="currency and price year"):
            plant.cost()
    assert Filter().cost() is None
