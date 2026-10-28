"""CO2 corrosion meta-model.

This module provides the high-level `CO2Corrosion` model that uses
different CO2 corrosion correlations. Based on the selected
`corrosion_model` parameter, it delegates the actual corrosion-rate
calculation to one of the following implementations in
`gemini.core.physics._legacy.corrosion.correlation`:

- `DLD`: de Waard–Lotz–Dugstad (1995)
- `DLM`: de Waard–Lotz–Milliams (1991)
- `NORSOK`: NORSOK M-506

The interface follows the common `Model` protocol used across Gemini.
Provide inputs `u` and optional state `x`, and set `parameters` including
`corrosion_model` and any model-specific parameters (e.g. `diameter`,
`roughness`).
"""

from gemini.core.physics._legacy.corrosion.correlation.dld_model import DLD
from gemini.core.physics._legacy.corrosion.correlation.dlm_model import DLM
from gemini.core.physics._legacy.corrosion.correlation.norsok_model import NORSOK
from gemini.core.physics._legacy.model_abstract import StaticModel


class CO2Corrosion(StaticModel):
    """CO2 corrosion rate model (dispatcher).

    Selects and runs one of the supported CO2 corrosion correlations
    (DLD, DLM, NORSOK) based on ``parameters['corrosion_model']`` and returns
    the computed corrosion rate.
    """

    def __init__(self):
        """Initialize CO2 corrosion model."""
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
        self.output = self.calculate_corrosion_rate(u, x)

    def get_output(self):
        """Get output of the model."""
        return self.output

    def calculate_corrosion_rate(self, u, x):
        """Calculate the corrosion rate."""
        model = self.parameters["corrosion_model"]

        if model == "DLD":
            corrosion_model = DLD()
        elif model == "DLM":
            corrosion_model = DLM()
        elif model == "NORSOK":
            corrosion_model = NORSOK()

        corrosion_model.update_parameters(self.parameters)
        corrosion_model.calculate_output(u, x)
        return corrosion_model.get_output()
