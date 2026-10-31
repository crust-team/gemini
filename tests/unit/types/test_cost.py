"""Cost aggregation never silently mixes valuation bases."""

import pytest

from gemini.modules import ModuleList
from gemini.modules.treatment.filter import Filter
from gemini.types.cost import Cost, total_cost


class CostedFilter(Filter):
    """Fictional cost for testing aggregation, not an equipment estimate."""

    def capex(self, assumptions):
        """Return a sourced fixture estimate."""
        return self.estimate


def test_cost_aggregation():
    """Costs sum all components only when currency and year match."""
    first, second = CostedFilter(), CostedFilter()
    first.estimate = Cost(
        capex=100, opex_fixed=10, opex_variable=0.001, price_year=2024, source="test fixture"
    )
    second.estimate = first.estimate
    plant = ModuleList([first, second])
    assert total_cost(plant, None).capex == 200
    assert total_cost(plant, None).opex_fixed == 20
    assert total_cost(plant, None).opex_variable == 0.002
    assert total_cost(plant, None).source == "test fixture"
    for change in ({"currency": "USD"}, {"price_year": 2025}):
        second.estimate = first.estimate.model_copy(update=change)
        with pytest.raises(ValueError, match="currency and price year"):
            total_cost(plant, None)
    assert total_cost(Filter(), None) is None
