"""Electric boiler unit (placeholder for electric boiler modules)."""

from gemini.core.base.unit import UnitAbstract


class ElectricBoilerUnit(UnitAbstract):
    """Electric boiler unit container for boiler modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize electric boiler unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
