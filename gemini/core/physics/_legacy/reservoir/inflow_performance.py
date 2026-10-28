"""Inflow performance relationship (IPR) model.

Computes bottomhole pressure for production or injection cases using
simple productivity/injectivity relations.
Reference: Tarek Ahmed, Chapter 7 - Oil Well Performance,
Editor(s): Tarek Ahmed, Reservoir Engineering Handbook (Fifth Edition),
Gulf Professional Publishing,2019,Pages 457-544,ISBN 9780128136492,
https://doi.org/10.1016/B978-0-12-813649-2.00007-4.

"""

from gemini.core.physics._legacy.model_abstract import StaticModel


class IPR(StaticModel):
    """Reservoir inflow performance calculator (production/injection)."""

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

        if self.parameters["type"] == "production_reservoir":
            Pbh = (
                self.parameters["reservoir_pressure"] - flow / self.parameters["productivity_index"]
            )
        elif self.parameters["type"] == "injection_reservoir":
            Pbh = (
                self.parameters["reservoir_pressure"] + flow / self.parameters["injectivity_index"]
            )

        self.output["bottomhole_pressure"] = Pbh

    def get_output(self):
        """Get output of the model."""
        return self.output
