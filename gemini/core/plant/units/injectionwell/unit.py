"""Injection-well monitoring unit using registry-discovered components."""

from gemini.core.base.unit import UnitAbstract
from gemini.core.engine.twin_modules.injectionwell import InjectionWellTwin


class InjectionWellUnit(UnitAbstract):
    """Injection unit providing pressure and injectivity monitoring."""

    def __init__(self, unit_id, unit_name, plant):
        """Attach the component-based injection monitoring module."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
        self.modules["model"] = [InjectionWellTwin(self)]
