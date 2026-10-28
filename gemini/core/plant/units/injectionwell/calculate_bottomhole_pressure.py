"""Calculate injection well bottomhole pressure via VLP from wellhead data."""

import traceback

import numpy as np

from gemini.core.base.unit_module import UnitModuleAbstract
from gemini.core.physics._legacy.fluid.pvt_water_stp import PVTConstantSTP
from gemini.core.physics._legacy.well.pressure_drop import DPDT


class CalculateBottomholePressure(UnitModuleAbstract):
    """Calculate bottomhole pressure for injection wells."""

    def __init__(self, unit):
        """Initialize bottomhole pressure calculation module."""
        super().__init__(unit)

        self.model = DPDT()
        self.model.PVT = PVTConstantSTP()

    def link(self):
        """Link module inputs and outputs."""
        self.link_input(self.unit, "measured", "injectionwell_flow")
        self.link_input(self.unit, "measured", "injectionwell_wellhead_pressure")
        self.link_input(self.unit, "measured", "injectionwell_wellhead_temperature")
        self.link_output(self.unit, "calculated", "injectionwell_bottomhole_pressure")

    def step(self, loop):
        """Execute module step calculation."""
        try:
            self.loop = loop
            self.loop.start_time = self.get_output_last_data_time(
                "injectionwell_bottomhole_pressure"
            )
            self.loop.compute_n_simulation()

            time, injectionwell_flow = self.get_input_data("injectionwell_flow")
            time, injectionwell_wellhead_pressure = self.get_input_data(
                "injectionwell_wellhead_pressure"
            )
            time, injectionwell_wellhead_temperature = self.get_input_data(
                "injectionwell_wellhead_temperature"
            )

            u = dict()
            injectionwell_bottomhole_pressure = []
            time_calc = []
            for ii in range(1, self.loop.n_step + 1):
                time_calc.append(time[ii])
                self.update_model_parameter(time[ii])

                if (
                    (injectionwell_flow[ii] is None)
                    or (injectionwell_wellhead_pressure[ii] is None)
                    or (injectionwell_wellhead_temperature[ii] is None)
                ):
                    injectionwell_bottomhole_pressure.append(None)
                    continue

                u["flowrate"] = -1 * injectionwell_flow[ii] / 3600
                u["pressure"] = injectionwell_wellhead_pressure[ii] * 1e5
                u["temperature"] = injectionwell_wellhead_temperature[ii] + 273.15
                u["direction"] = "down"
                u["temperature_ambient"] = self.model.parameters["soil_temperature"] + 273.15

                x = []
                self.model.calculate_output(u, x)

                y = self.model.get_output()

                injectionwell_bottomhole_pressure.append(y["pressure_output"] / 1e5)

            if time_calc:
                self.write_output_data(
                    "injectionwell_bottomhole_pressure",
                    time_calc,
                    injectionwell_bottomhole_pressure,
                )

        except Exception:
            self.logger.warn(
                "ERROR in module " + self.__class__.__name__ + " : " + traceback.format_exc()
            )

    def update_model_parameter(self, timestamp):
        """Update model parameters for given timestamp."""
        reservoir_unit = self.unit.to_units[0]

        well_index = self.get_parameter_index(self.unit, timestamp)
        reservoir_index = self.get_parameter_index(reservoir_unit, timestamp)

        well_param = dict()
        well_param["soil_temperature"] = self.unit.parameters["property"][
            "injectionwell_soil_temperature"
        ][well_index]

        well_traj = self.unit.parameters["property"]["injectionwell_trajectory_table"][well_index]
        length = []
        diameter = []
        angle = []
        roughness = []
        for ii in range(1, len(well_traj)):
            MD = well_traj[ii]["MD"] - well_traj[ii - 1]["MD"]
            TVD = well_traj[ii]["TVD"] - well_traj[ii - 1]["TVD"]

            length.append(MD)
            diameter.append(well_traj[ii]["ID"])
            angle.append((np.round(90 - np.arccos(TVD / MD) * 180 / np.pi, 2)) * np.pi / 180)
            roughness.append(well_traj[ii]["roughness"])

        well_param["diameter"] = np.array(diameter)  # well diameter in [m]
        well_param["length"] = np.array(length)  # well length in [m]
        well_param["angle"] = np.array(angle)  # well angle in [degree]
        well_param["roughness"] = roughness  # roughness of cells (mm)
        well_param["friction_correlation"] = self.unit.parameters["property"][
            "injectionwell_friction_correlation"
        ][well_index]
        well_param["friction_correlation_2p"] = self.unit.parameters["property"][
            "injectionwell_friction_correlation_2p"
        ][well_index]
        well_param["correction_factors"] = self.unit.parameters["property"][
            "injectionwell_friction_correction_factors"
        ][well_index]

        self.model.update_parameters(well_param)

        pvt_param = dict()
        pvt_param["RHOL"] = reservoir_unit.parameters["property"]["liquid_density"][reservoir_index]
        pvt_param["VISL"] = reservoir_unit.parameters["property"]["liquid_viscosity"][
            reservoir_index
        ]

        self.model.PVT.update_parameters(pvt_param)
