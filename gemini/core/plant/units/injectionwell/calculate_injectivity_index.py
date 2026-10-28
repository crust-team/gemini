"""Calculate injectivity index from flow and bottomhole pressure."""

import traceback

from gemini.core.base.unit_module import UnitModuleAbstract
from gemini.core.physics._legacy.reservoir.injectivity_index import injectivity_index


class CalculateInjectivityIndex(UnitModuleAbstract):
    """Calculate injectivity index for injection wells."""

    def __init__(self, unit):
        """Initialize injectivity index calculation module."""
        super().__init__(unit)

        self.model = injectivity_index()

    def link(self):
        """Link module inputs and outputs."""
        self.link_input(self.unit, "measured", "injectionwell_flow")
        self.link_input(self.unit, "calculated", "injectionwell_bottomhole_pressure")
        self.link_output(self.unit, "calculated", "injectionwell_injectivity_index")

    def step(self, loop):
        """Execute module step calculation."""
        try:
            self.loop = loop
            self.loop.start_time = self.get_output_last_data_time("injectionwell_injectivity_index")
            self.loop.compute_n_simulation()

            time, injectionwell_flow = self.get_input_data("injectionwell_flow")
            time, injectionwell_bottomhole_pressure = self.get_input_data(
                "injectionwell_bottomhole_pressure"
            )

            u = dict()
            injectivity_index = []
            time_calc = []
            for ii in range(1, self.loop.n_step + 1):
                time_calc.append(time[ii])
                self.update_model_parameter(time[ii])

                if (injectionwell_flow[ii] is None) or (
                    injectionwell_bottomhole_pressure[ii] is None
                ):
                    injectivity_index.append(None)
                    continue

                u["flow"] = injectionwell_flow[ii]
                u["bottomhole_pressure"] = injectionwell_bottomhole_pressure[ii]

                x = []
                self.model.calculate_output(u, x)

                y = self.model.get_output()

                injectivity_index.append(y["injectivity_index"])

            if time_calc:
                self.write_output_data(
                    "injectionwell_injectivity_index", time_calc, injectivity_index
                )
        except Exception:
            self.logger.warn(
                "ERROR in module " + self.__class__.__name__ + " : " + traceback.format_exc()
            )

    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        reservoir_unit = self.unit.to_units[0]

        reservoir_index = self.get_parameter_index(reservoir_unit, timestamp)

        res_param = dict()
        res_param["reservoir_pressure"] = reservoir_unit.parameters["property"][
            "reservoir_pressure"
        ][reservoir_index]

        self.model.update_parameters(res_param)
