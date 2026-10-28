"""Calculate ESP outlet pressure via VLP from wellhead conditions to ESP depth."""

import traceback

import numpy as np

from gemini.core.base.unit_module import UnitModuleAbstract
from gemini.core.physics._legacy.fluid.pvt_water_stp import PVTConstantSTP
from gemini.core.physics._legacy.pump.esp import ESP
from gemini.core.physics._legacy.well.pressure_drop import DPDT


class CalculateVLPOutletPressure(UnitModuleAbstract):
    """Compute ESP outlet pressure using VLP and wellhead measurements."""

    def __init__(self, unit):
        """Initialize VLP outlet pressure calculation module."""
        super().__init__(unit)

        self.model = ESP()
        self.VLP1 = DPDT()
        self.VLP1.PVT = PVTConstantSTP()

    def link(self):
        """Link module inputs and outputs."""
        well_unit = self.unit.from_units[0]

        self.link_input(self.unit, "measured", "esp_flow")
        self.link_input(well_unit, "measured", "productionwell_wellhead_pressure")
        self.link_input(well_unit, "measured", "productionwell_wellhead_temperature")
        self.link_output(self.unit, "calculated", "esp_vlp_outlet_pressure")

    def step(self, loop):
        """Execute module step calculation."""
        try:
            self.loop = loop
            self.loop.start_time = self.get_output_last_data_time("esp_vlp_outlet_pressure")
            self.loop.compute_n_simulation()

            # Get well data
            time, wellhead_pressure = self.get_input_data("productionwell_wellhead_pressure")
            time, wellhead_temperature = self.get_input_data("productionwell_wellhead_temperature")
            time, well_flow = self.get_input_data("esp_flow")

            """Calculate discharge pressure via the pressure dop from wellhead to ESP"""
            u = dict()
            discharge_pressure = []
            time_calc = []
            for ii in range(1, self.loop.n_step + 1):
                time_calc.append(time[ii])
                self.update_model_parameter(time[ii])

                esp_correction_factor_str = self.unit.parameters["property"][
                    "esp_correction_factor"
                ][0]
                esp_correction_factor = np.asarray(
                    esp_correction_factor_str.split(";"), dtype=np.float32
                )  # esp_correction_factor a * x + b

                if (
                    (wellhead_pressure[ii] is None)
                    or (wellhead_temperature[ii] is None)
                    or (well_flow[ii] is None)
                ):
                    discharge_pressure.append(None)
                    continue

                u["pressure"] = wellhead_pressure[ii] * 1e5  # bar to Pa
                u["temperature"] = wellhead_temperature[ii] + 273.15  # C to K
                u["flowrate"] = well_flow[ii] / 3600  # m3/hr to m3/s
                u["temperature_ambient"] = (
                    self.VLP1.parameters["soil_temperature"] + 273.15
                )  # C to K
                u["direction"] = "down"

                x = []
                self.VLP1.calculate_output(u, x)

                # ASSERT
                y = self.VLP1.get_output()

                discharge_pressure.append(
                    esp_correction_factor[0] * (y["pressure_output"] / 1e5)
                    + esp_correction_factor[1]
                )  # Pa to bar

            if time_calc:
                self.write_output_data("esp_vlp_outlet_pressure", time_calc, discharge_pressure)
        except Exception:
            self.logger.warn(
                "ERROR in module " + self.__class__.__name__ + " : " + traceback.format_exc()
            )

    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        esp_unit = self.unit
        well_unit = self.unit.from_units[0]
        reservoir_unit = well_unit.from_units[0]

        esp_index = self.get_parameter_index(esp_unit, timestamp)
        well_index = self.get_parameter_index(well_unit, timestamp)
        reservoir_index = self.get_parameter_index(reservoir_unit, timestamp)

        well_param = dict()
        well_param["soil_temperature"] = well_unit.parameters["property"][
            "productionwell_soil_temperature"
        ][well_index]

        well_param["diameter"] = np.array(
            [esp_unit.parameters["property"]["esp_tubing"][esp_index]]
        )  # well diameter in [m]
        well_param["length"] = np.array(
            [esp_unit.parameters["property"]["esp_depth"][esp_index]]
        )  # well depth in [m]
        well_param["angle"] = np.array([90 * np.pi / 180])  # well angle in [degree]
        well_traj = well_unit.parameters["property"]["productionwell_trajectory_table"][well_index]
        well_param["roughness"] = np.array([well_traj[1]["roughness"]])  # roughness of cells [m]
        well_param["friction_correlation"] = well_unit.parameters["property"][
            "productionwell_friction_correlation"
        ][well_index]
        well_param["friction_correlation_2p"] = well_unit.parameters["property"][
            "productionwell_friction_correlation_2p"
        ][well_index]
        well_param["correction_factors"] = well_unit.parameters["property"][
            "productionwell_friction_correction_factors"
        ][well_index]

        self.VLP1.update_parameters(well_param)

        pvt_param = dict()
        pvt_param["RHOL"] = reservoir_unit.parameters["property"]["liquid_density"][reservoir_index]
        pvt_param["VISL"] = reservoir_unit.parameters["property"]["liquid_viscosity"][
            reservoir_index
        ]

        self.VLP1.PVT.update_parameters(pvt_param)
