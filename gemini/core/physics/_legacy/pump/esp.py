"""Electrical submersible pump (ESP) model.

Implements simple correlations to predict pump head, power, and efficiency
as a function of flow rate and frequency.
Reference: TNO 2022 R11363 "Model-based monitoring of geothermal assets,
case study: electrical submersible pumps".
"""

from typing import NotRequired, TypedDict

from gemini.core.physics._legacy.model_abstract import StaticModel


class ESPParameters(TypedDict):
    """Required parameter schema for ESP."""

    no_stages: float
    head_coeff: list[float]
    power_coeff: list[float]
    pump_name: NotRequired[str]


class ESPInput(TypedDict):
    """Runtime input schema for ESP."""

    pump_freq: float
    pump_flow: float


class ESP(StaticModel):
    """ESP performance model (head, power, efficiency)."""

    M3S_TO_BBLD = 543439.650564
    FT_HEAD_TO_PA = 2988.30167
    BHP_TO_WATT = 745.7
    EFFICIENCY_FLOW_FACTOR = 135773
    _POLY_ORDER = 6

    def __init__(self):
        """Model initialization."""
        super().__init__()

    def update_parameters(self, parameters: dict):
        """Update model parameters.

        Parameters
        ----------
        parameters: dict
            Parameters dict as defined by the model.
        """
        super().update_parameters(parameters)
        self._validate_parameters()

    def calculate_output(self, u, x=None):
        """Calculate output based on input u (stateless model)."""
        self._validate_inputs(u)
        # get input
        pump_freq = u["pump_freq"]
        pump_flow = u["pump_flow"]

        # calculate model
        pump_head = self.head_function(pump_flow, pump_freq)
        pump_power = self.power_function(pump_flow, pump_freq)
        pump_eff = self.efficiency_function(pump_flow, pump_head, pump_power)

        # write output
        self.output["pump_head"] = pump_head
        self.output["pump_power"] = pump_power
        self.output["pump_eff"] = pump_eff

    def head_function(self, pump_flow, freq):
        """Calculate ESP head from flow and frequency (uses US-unit correlation)."""
        pump_flow = pump_flow * self.M3S_TO_BBLD  # m3/s to bbl/d
        head = (
            self.parameters["no_stages"]
            * ((freq / 60) ** 2)
            * self._eval_poly(self.parameters["head_coeff"], pump_flow)
        )
        return head * self.FT_HEAD_TO_PA  # feet of head to Pa

    def power_function(self, pump_flow, freq):
        """Calculate ESP power from flow and frequency (US-unit correlation)."""
        pump_flow = pump_flow * self.M3S_TO_BBLD  # m3/s to bbl/d
        pump_power = (
            self.parameters["no_stages"]
            * ((freq / 60) ** 3)
            * self._eval_poly(self.parameters["power_coeff"], pump_flow)
        )
        return pump_power * self.BHP_TO_WATT  # brake horsepower to Watts

    def efficiency_function(self, pump_flow, pump_head, pump_power):
        """Calculate ESP efficiency from flow, head, and power (US-unit correlation)."""
        pump_flow = pump_flow * self.M3S_TO_BBLD  # m3/s to bbl/d

        if pump_power < 0.1:
            pump_eff = 0
        else:
            pump_eff = (
                100
                * pump_flow
                / self.EFFICIENCY_FLOW_FACTOR
                * (pump_head / pump_power)
                * (self.BHP_TO_WATT / self.FT_HEAD_TO_PA)
            )

        return pump_eff

    def _validate_parameters(self):
        """Validate required parameters and coefficient shape."""
        missing = [
            key for key in ("no_stages", "head_coeff", "power_coeff") if key not in self.parameters
        ]
        if missing:
            raise KeyError(f"Missing ESP parameters: {missing}")

        for key in ("head_coeff", "power_coeff"):
            coeff = self.parameters[key]
            if len(coeff) != self._POLY_ORDER:
                raise ValueError(
                    f"Parameter '{key}' must have {self._POLY_ORDER} "
                    f"coefficients, got {len(coeff)}."
                )

    @staticmethod
    def _eval_poly(coefficients, value):
        """Evaluate polynomial sum(c_i * value**i)."""
        return sum(coef * (value**order) for order, coef in enumerate(coefficients))

    @staticmethod
    def _validate_inputs(u):
        """Validate runtime inputs for ESP calculations."""
        missing = [key for key in ("pump_freq", "pump_flow") if key not in u]
        if missing:
            raise KeyError(f"Missing ESP inputs: {missing}")
