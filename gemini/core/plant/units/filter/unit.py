"""Filter unit (placeholder for filter modules)."""

from gemini.core.base.unit import UnitAbstract


class FilterUnit(UnitAbstract):
    """Filter unit container for filter modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize filter unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
