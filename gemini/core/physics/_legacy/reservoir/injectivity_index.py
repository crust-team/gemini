"""Injectivity index calculator.

Computes injectivity from measured bottomhole pressure and flow.
Reference: R. Arnold (2021), Analytics-Driven Method for Injectivity Analysis
in Tight and Heterogeneous Waterflooded Reservoir, Proceedings joint convention Bandung.
"""

from gemini.core.physics._legacy.model_abstract import StaticModel


class injectivity_index(StaticModel):
    """Calculate injectivity index from flow and pressure differential."""

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
        # get input
        flow = u["flow"]
        p_bh = u["bottomhole_pressure"]

        delta_P = p_bh - self.parameters["reservoir_pressure"]
        II = flow / delta_P

        self.output["injectivity_index"] = II

    def get_output(self):
        """Get output of the model."""
        return self.output
