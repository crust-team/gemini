"""Degasser unit (placeholder for degasser modules)."""

from gemini.core.base.unit import UnitAbstract


class DegasserUnit(UnitAbstract):
    """Degasser unit container for degasser modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize degasser unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
