"""Calculate ESP head via VLP-based outlet minus inlet pressure."""

import traceback

from gemini.core.base.unit_module import UnitModuleAbstract
from gemini.core.physics._legacy.pump.esp import ESP


class CalculateVLPHead(UnitModuleAbstract):
    """Compute ESP head as VLP outlet pressure minus measured inlet pressure."""

    def __init__(self, unit):
        """Initialize VLP head calculation module."""
        super().__init__(unit)

        self.model = ESP()

    def link(self):
        """Link module inputs and outputs."""
        self.link_input(self.unit, "measured", "esp_inlet_pressure")
        self.link_input(self.unit, "calculated", "esp_vlp_outlet_pressure")
        self.link_output(self.unit, "calculated", "esp_vlp_head")

    def step(self, loop):
        """Execute module step calculation."""
        try:
            self.loop = loop
            self.loop.start_time = self.get_output_last_data_time("esp_vlp_head")
            self.loop.compute_n_simulation()

            time, esp_intake = self.get_input_data("esp_inlet_pressure")
            time, esp_discharge = self.get_input_data("esp_vlp_outlet_pressure")

            esp_vlp_head = []
            time_calc = []
            for ii in range(1, self.loop.n_step + 1):
                time_calc.append(time[ii])

                if (esp_discharge[ii] is None) or (esp_intake[ii] is None):
                    esp_vlp_head.append(None)
                    continue

                esp_head = esp_discharge[ii] - esp_intake[ii]

                esp_vlp_head.append(esp_head)

            if time_calc:
                self.write_output_data("esp_vlp_head", time_calc, esp_vlp_head)

        except Exception:
            self.logger.warn(
                "ERROR in module " + self.__class__.__name__ + " : " + traceback.format_exc()
            )

    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        pass
