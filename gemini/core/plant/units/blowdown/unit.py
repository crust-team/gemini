"""Blowdown unit (placeholder for blowdown modules)."""

from gemini.core.base.unit import UnitAbstract


class BlowdownUnit(UnitAbstract):
    """Blowdown unit container for blowdown modules."""

    def __init__(self, unit_id, unit_name, plant):
        """Initialize blowdown unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
