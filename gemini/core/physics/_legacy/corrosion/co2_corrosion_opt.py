"""CO2 corrosion meta-model (optimized implementations).

This module is similar to ``co2_corrosion`` but dispatches to optimized
implementations under ``correlations_opt``. The public behavior is the same:
set ``parameters['corrosion_model']`` to one of ``'DLD'``, ``'DLM'``, or
``'NORSOK'`` and call :meth:`calculate_output` to obtain the corrosion rate.
"""

from gemini.core.physics._legacy.corrosion.correlations_opt.dld_model_opt import DLD
from gemini.core.physics._legacy.corrosion.correlations_opt.dlm_model_opt import DLM
from gemini.core.physics._legacy.corrosion.correlations_opt.norsok_model_opt import NORSOK
from gemini.core.physics._legacy.model_abstract import StaticModel


class CO2CorrosionOpt(StaticModel):
    """CO2 corrosion rate model using optimized correlation implementations."""

    def __init__(self):
        """Initialize CO2 corrosion optimization model."""
        self.parameters = {}
        self.output = {}
        # Cache correlation instances so they are built once, not per call
        # (the calibration loop evaluates this model many times per joint).
        self._correlation_cache = {}

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
        # -- reuse a cached correlation instance (hot-loop friendly) --------
        model = self.parameters["corrosion_model"]
        corrosion_model = self._correlation_cache.get(model)
        if corrosion_model is None:
            if model == "DLD":
                corrosion_model = DLD()
            elif model == "DLM":
                corrosion_model = DLM()
            elif model == "NORSOK":
                corrosion_model = NORSOK()
            else:
                raise ValueError(f"Unknown corrosion_model '{model}'.")
            self._correlation_cache[model] = corrosion_model

        # -- run with the current parameters --------------------------------
        corrosion_model.update_parameters(self.parameters)
        corrosion_model.calculate_output(u, x)
        return corrosion_model.get_output()
