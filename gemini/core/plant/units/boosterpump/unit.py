"""Booster pump unit (placeholder for booster pump modules)."""

from gemini.core.base.unit import UnitAbstract


class BoosterPumpUnit(UnitAbstract):
    """Booster pump unit container for booster pump modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize booster pump unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
