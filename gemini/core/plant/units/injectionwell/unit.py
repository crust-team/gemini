"""Injection well unit: injectivity and bottomhole pressure modules."""

from gemini.core.base.unit import UnitAbstract
from gemini.core.plant.units.injectionwell.calculate_bottomhole_pressure import (
    CalculateBottomholePressure,
)
from gemini.core.plant.units.injectionwell.calculate_injectivity_index import (
    CalculateInjectivityIndex,
)


class InjectionWellUnit(UnitAbstract):
    """Injection well unit includes bottomhole pressure and injectivity modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize injection well unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)

        # define unit modules
        self.modules["model"].append(CalculateBottomholePressure(self))
        self.modules["model"].append(CalculateInjectivityIndex(self))
