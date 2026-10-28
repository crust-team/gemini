"""Calculate ESP inlet pressure via IPR for reservoir and VLP for tubing."""

import traceback

import numpy as np

from gemini.core.base.unit_module import UnitModuleAbstract
from gemini.core.physics._legacy.fluid.pvt_water_stp import PVTConstantSTP
from gemini.core.physics._legacy.pump.esp import ESP
from gemini.core.physics._legacy.reservoir.inflow_performance import IPR
from gemini.core.physics._legacy.well.pressure_drop import DPDT


class CalculateVLPIPRInletPressure(UnitModuleAbstract):
    """Calculate VLP IPR inlet pressure for ESP units."""

    def __init__(self, unit):
        """Initialize VLP IPR inlet pressure calculation module."""
        super().__init__(unit)

        self.model = ESP()
        self.VLP = DPDT()
        self.VLP.PVT = PVTConstantSTP()
        self.IPR = IPR()

    def link(self):
        """Link module inputs and outputs."""
        self.link_input(self.unit, "measured", "esp_flow")
        self.link_output(self.unit, "calculated", "esp_vlp_ipr_inlet_pressure")

    def step(self, loop):
        """Execute module step calculation."""
        try:
            self.loop = loop
            self.loop.start_time = self.get_output_last_data_time("esp_vlp_ipr_inlet_pressure")
            self.loop.compute_n_simulation()

            time, esp_flow = self.get_input_data("esp_flow")  # m3/hr

            """Calculate bottomhole pressure from reservoir"""
            u = dict()

            pbh_res = []
            time_calc = []
            for ii in range(0, self.loop.n_step + 1):
                time_calc.append(time[ii])
                self.update_model_parameter(time[ii])

                if esp_flow[ii] is None:
                    pbh_res.append(None)
                    continue
                u["flow"] = esp_flow[ii] / 3600  # convert to seconds

                x = []
                self.IPR.calculate_output(u, x)

                # ASSERT
                y = self.IPR.get_output()

                pbh_res.append(y["bottomhole_pressure"])

            """Calculate pressure drop from bottomhole to ESP"""
            u = dict()

            intake_pressure = []
            time_calc = []
            for ii in range(1, self.loop.n_step + 1):
                time_calc.append(time[ii])
                self.update_model_parameter(time[ii])

                if (esp_flow[ii] is None) or (pbh_res[ii] is None):
                    intake_pressure.append(None)
                    continue

                u["pressure"] = pbh_res[ii] * 1e5
                u["temperature"] = self.IPR.parameters["reservoir_temperature"] + 273.15  # C to K
                u["flowrate"] = esp_flow[ii] / 3600  # m3/hr to m3/s
                u["temperature_ambient"] = (
                    self.VLP.parameters["soil_temperature"] + 273.15
                )  # C to K
                u["direction"] = "up"

                x = []
                self.VLP.calculate_output(u, x)

                # ASSERT
                y = self.VLP.get_output()

                intake_pressure.append(y["pressure_output"] / 1e5)  # Pa to bar

            if time_calc:
                self.write_output_data("esp_vlp_ipr_inlet_pressure", time_calc, intake_pressure)

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

        well_traj = well_unit.parameters["property"]["productionwell_trajectory_table"][well_index]
        length = []
        diameter = []
        angle = []
        roughness = []
        for ii in range(1, len(well_traj)):
            if well_traj[ii - 1]["MD"] >= esp_unit.parameters["property"]["esp_depth"][esp_index]:
                MD = well_traj[ii]["MD"] - well_traj[ii - 1]["MD"]
                TVD = well_traj[ii]["TVD"] - well_traj[ii - 1]["TVD"]

                length.append(MD)
                diameter.append(well_traj[ii]["ID"])
                angle.append(np.round(90 - np.arccos(TVD / MD) * 180 / np.pi, 2) * np.pi / 180)
                roughness.append(well_traj[ii]["roughness"])

        well_param["diameter"] = np.array(diameter)  # well diameter in [m]
        well_param["length"] = np.array(length)  # well depth in [m]
        well_param["angle"] = np.array(angle)  # well angle in [degree]
        well_param["roughness"] = roughness  # roughness of cells [m]
        well_param["friction_correlation"] = well_unit.parameters["property"][
            "productionwell_friction_correlation"
        ][well_index]
        well_param["friction_correlation_2p"] = well_unit.parameters["property"][
            "productionwell_friction_correlation_2p"
        ][well_index]
        well_param["correction_factors"] = well_unit.parameters["property"][
            "productionwell_friction_correction_factors"
        ][well_index]

        self.VLP.update_parameters(well_param)

        pvt_param = dict()
        pvt_param["RHOL"] = reservoir_unit.parameters["property"]["liquid_density"][reservoir_index]
        pvt_param["VISL"] = reservoir_unit.parameters["property"]["liquid_viscosity"][
            reservoir_index
        ]

        self.VLP.PVT.update_parameters(pvt_param)

        res_param = dict()
        res_param["reservoir_pressure"] = reservoir_unit.parameters["property"][
            "reservoir_pressure"
        ][reservoir_index]
        res_param["reservoir_temperature"] = reservoir_unit.parameters["property"][
            "reservoir_temperature"
        ][reservoir_index]
        res_param["productivity_index"] = well_unit.parameters["property"][
            "productionwell_productivity_index"
        ][well_index]
        res_param["type"] = "production_reservoir"

        self.IPR.update_parameters(res_param)
