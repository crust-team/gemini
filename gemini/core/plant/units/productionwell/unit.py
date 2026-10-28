"""Production well unit (placeholder for production-related modules)."""

from gemini.core.base.unit import UnitAbstract


class ProductionWellUnit(UnitAbstract):
    """Production well unit container for production modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize production well unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
