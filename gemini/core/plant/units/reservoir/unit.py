"""Reservoir unit (placeholder for reservoir-related modules)."""

from gemini.core.base.unit import UnitAbstract


class ReservoirUnit(UnitAbstract):
    """Reservoir unit container for reservoir modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize reservoir unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
