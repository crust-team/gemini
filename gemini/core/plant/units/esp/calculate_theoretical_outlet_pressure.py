"""Calculate theoretical ESP outlet pressure by adding theoretical head to inlet."""

import traceback

from gemini.core.base.unit_module import UnitModuleAbstract
from gemini.core.physics._legacy.pump.esp import ESP


class CalculateTheoreticalOutletPressure(UnitModuleAbstract):
    """Add theoretical pump head to measured inlet to estimate outlet pressure."""

    def __init__(self, unit):
        """Initialize theoretical outlet pressure calculation module."""
        super().__init__(unit)

        self.model = ESP()

    def link(self):
        """Link module inputs and outputs."""
        self.link_input(self.unit, "measured", "esp_inlet_pressure")
        self.link_input(self.unit, "calculated", "esp_theoretical_head")
        self.link_output(self.unit, "calculated", "esp_theoretical_outlet_pressure")

    def step(self, loop):
        """Execute module step calculation."""
        try:
            self.loop = loop
            self.loop.start_time = self.get_output_last_data_time("esp_theoretical_outlet_pressure")
            self.loop.compute_n_simulation()

            time, esp_inlet = self.get_input_data("esp_inlet_pressure")
            time, esp_theoretical_head = self.get_input_data("esp_theoretical_head")

            esp_outlet = []
            time_calc = []
            for ii in range(1, self.loop.n_step + 1):
                time_calc.append(time[ii])
                if (esp_theoretical_head[ii] is None) or (esp_inlet[ii] is None):
                    esp_outlet.append(None)
                    continue

                esp_head = esp_theoretical_head[ii] + esp_inlet[ii]

                esp_outlet.append(esp_head)

            if time_calc:
                self.write_output_data("esp_theoretical_outlet_pressure", time_calc, esp_outlet)

        except Exception:
            self.logger.warn(
                "ERROR in module " + self.__class__.__name__ + " : " + traceback.format_exc()
            )

    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        pass
