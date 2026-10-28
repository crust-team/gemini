"""ESP monitoring unit; physics lives in registry-discovered components."""

from gemini.core.base.unit import UnitAbstract
from gemini.core.engine.twin_modules.esp_theoretical import ESPTheoretical
from gemini.core.engine.twin_modules.esp_vlp import ESPVLP


class ESPUnit(UnitAbstract):
    """ESP unit providing theoretical and inferred pressure tags."""

    def __init__(self, unit_id, unit_name, plant):
        """Attach component-based monitoring modules to the unit."""
        super().__init__(unit_id=unit_id, unit_name=unit_name, plant=plant)
        self.modules["model"] = [ESPTheoretical(self), ESPVLP(self)]
