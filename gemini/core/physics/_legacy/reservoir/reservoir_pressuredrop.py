"""Bottomhole and reservoir pressure drop calculations with skin and hydrostatic.

Computes pressure components due to radial flow (Darcy), skin, and hydrostatic
column for given reservoir and fluid parameters.
Reference: Akin (2019), Geothermal re-injection performance evaluation
using surveillance analysis methods. Renewable Energy. https://doi.org/10.1016/j.renene.2019.03.103
"""

import numpy as np

from gemini.core.physics._legacy.model_abstract import StaticModel


class bottomhole_skin_dp(StaticModel):
    """Calculate bottomhole/reservoir dp including skin and hydrostatic terms."""

    def __init__(self):
        """Model initialization."""
        self.parameters = {}
        self.output = {}

    def update_parameters(self, parameters):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model.
        """
        for key, value in parameters.items():
            self.parameters[key] = value

    def initialize_state(self, x):
        """Generate an initial state based on user parameters."""
        pass

    def update_state(self, u, x):
        """Update the state based on input u and state x."""
        pass

    def calculate_output(self, u, x):
        """Calculate output based on input u and state x."""
        # constant
        g = 9.81

        # get input
        flow = u["flow"]
        viscosity = u["viscosity"]
        density = u["density"]
        well_radius = u["well_radius"]
        skin_factor = u["skin_factor"]

        reservoir_pressure = self.parameters["reservoir_pressure"]
        reservoir_radius = self.parameters["reservoir_radius"]
        reservoir_permeability = self.parameters["reservoir_permeability"]
        reservoir_thickness = self.parameters["reservoir_thickness"]
        reservoir_top = self.parameters["reservoir_top"]

        deltaP_flow = (flow * viscosity * np.log(reservoir_radius / well_radius)) / (
            2 * np.pi * reservoir_permeability * reservoir_thickness
        )

        deltaP_skin = (flow * viscosity * skin_factor) / (
            2 * np.pi * reservoir_permeability * reservoir_thickness
        )

        deltaP_HH = reservoir_top * density * g

        self.output["Hydrostatic_dp"] = deltaP_HH
        self.output["skin_dp"] = deltaP_skin
        self.output["bottomhole_dp"] = deltaP_flow
        self.output["reservoir_dp"] = reservoir_pressure + deltaP_flow + deltaP_skin

    def get_output(self):
        """Get output of the model."""
        return self.output
