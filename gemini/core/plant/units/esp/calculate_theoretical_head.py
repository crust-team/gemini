"""Calculate theoretical ESP head from flow/frequency and pump coefficients."""

import traceback

import numpy as np

from gemini.core.base.unit_module import UnitModuleAbstract
from gemini.core.physics._legacy.pump.esp import ESP


class CalculateTheoreticalHead(UnitModuleAbstract):
    """Compute theoretical ESP head using head coefficients, flow, and frequency."""

    def __init__(self, unit):
        """Initialize theoretical head calculation module."""
        super().__init__(unit)

        self.model = ESP()

    def link(self):
        """Link module inputs and outputs."""
        self.link_input(self.unit, "measured", "esp_flow")
        self.link_input(self.unit, "measured", "esp_frequency")
        self.link_output(self.unit, "calculated", "esp_theoretical_head")

    def step(self, loop):
        """Execute module step calculation."""
        try:
            self.loop = loop
            self.loop.start_time = self.get_output_last_data_time("esp_theoretical_head")
            self.loop.compute_n_simulation()

            time, esp_flow = self.get_input_data("esp_flow")
            time, esp_frequency = self.get_input_data("esp_frequency")

            u = dict()
            esp_pump_head = []
            time_calc = []
            for ii in range(1, self.loop.n_step + 1):
                time_calc.append(time[ii])
                self.update_model_parameter(time[ii])

                if (esp_flow[ii] is None) or (esp_frequency[ii] is None):
                    esp_pump_head.append(None)
                    continue

                u["pump_flow"] = esp_flow[ii] / 3600  # convert to seconds
                u["pump_freq"] = esp_frequency[ii]

                x = []
                self.model.calculate_output(u, x)

                y = self.model.get_output()

                esp_pump_head.append(y["pump_head"] / 1e5)  # convert to bar

            if time_calc:
                self.write_output_data("esp_theoretical_head", time_calc, esp_pump_head)

        except Exception:
            self.logger.warn(
                "ERROR in module " + self.__class__.__name__ + " : " + traceback.format_exc()
            )

    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        index = self.get_parameter_index(self.unit, timestamp)

        esp_param = dict()
        esp_param["no_stages"] = self.unit.parameters["property"]["esp_no_stage"][index]
        esp_param["pump_name"] = self.unit.parameters["property"]["esp_type"][index]
        esp_param["head_coeff"] = np.asarray(
            self.unit.parameters["property"]["esp_head_coeff"][index].split(";"), dtype=np.float32
        )
        esp_param["power_coeff"] = np.asarray(
            self.unit.parameters["property"]["esp_power_coeff"][index].split(";"), dtype=np.float32
        )

        self.model.update_parameters(esp_param)
