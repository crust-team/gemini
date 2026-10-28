"""Reservoir pressure estimation from slope plot.

Estimates reservoir pressure via linear regression on p/Q vs 1/Q derived from
flow and bottomhole pressure measurements.
Reference: Akin (2019), Geothermal re-injection performance evaluation
using surveillance analysis methods. Renewable Energy. https://doi.org/10.1016/j.renene.2019.03.103
"""

import numpy as np

from gemini.core.physics._legacy.model_abstract import StaticModel


class reservoir_pressure(StaticModel):
    """Estimate reservoir pressure from p/Q vs 1/Q regression."""

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
        """Estimate reservoir pressure from arrays of flow and bottomhole pressure.

        Uses linear regression.
        """
        flow = u["flow"]
        p_bh = u["bottomhole_pressure"]

        # Calculate p/Q and 1/Q for regression
        p_over_Q = p_bh / flow
        inv_Q = 1 / flow

        # Linear fit
        fit_params = np.polyfit(inv_Q, p_over_Q, 1)
        fit_function = np.poly1d(fit_params)

        # Calculate R-squared
        residuals = p_over_Q - fit_function(inv_Q)
        ss_residuals = np.sum(residuals**2)
        ss_total = np.sum((p_over_Q - np.mean(p_over_Q)) ** 2)
        r_squared = 1 - (ss_residuals / ss_total)

        res_press = fit_params[0]

        self.output["reservoir_pressure"] = res_press
        self.output["r_squared"] = r_squared

    def get_output(self):
        """Get output of the model."""
        return self.output
