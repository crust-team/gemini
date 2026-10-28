"""Gas boiler unit (placeholder for gas boiler modules)."""

from gemini.core.base.unit import UnitAbstract


class GasBoilerUnit(UnitAbstract):
    """Gas boiler unit container for boiler modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize gas boiler unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
