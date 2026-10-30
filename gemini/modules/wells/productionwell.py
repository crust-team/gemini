"""Production well from the sandface to the wellhead, optionally split at an internal ESP."""

from typing import Literal

from gemini.errors import ValidationError
from gemini.modules.wells.well import _Well
from gemini.physics import fluid, heat_transfer
from gemini.types import (
    HeatLoss,
    Inlet,
    Length,
    Outlet,
    Output,
    Parameter,
    Pressure,
    PressureDifference,
    Stream,
    Temperature,
)


class ProductionWell(_Well):
    """Production-well pressure and temperature profile with integrity checks.

    ``segment`` selects the traversed interval: the full well, the part below an internal ESP
    (sandface to intake) or the part above it (discharge to wellhead).

    NOTE(refactor): ``esp_depth`` is structural: it cuts the pipe path. The ``section_pressure``
    and ``section_temperature`` list outputs are vector outputs of the graph, one item per
    section.
    """

    repr_fields = ("segment", "esp_depth", "soil_temperature", "heat_transfer_coefficient")

    def __init__(self):
        """Declare production-well geometry, inlet and outputs."""
        super().__init__()

        # Parameters
        self.segment = Parameter(Literal["full", "below_esp", "above_esp"], default="full")
        self.esp_depth = Parameter(Length | None, default=None, structural=True)

        # Inlets
        self.bottom = Inlet(Stream, stream="brine")

        # Outputs
        self.wellhead_pressure = Output(Pressure, soft_sensor=True)
        self.wellhead_temperature = Output(Temperature, soft_sensor=True)
        self.friction_pressure_drop = Output(PressureDifference)
        self.gravity_pressure_drop = Output(PressureDifference)
        self.section_pressure = Output(list[Pressure])
        self.section_temperature = Output(list[Temperature])
        self.heat_loss = Output(HeatLoss)

        # Outlets
        self.wellhead = Outlet(Stream, stream="brine")

    def forward(self, inlets):
        """Traverse the selected segment upward and apply the pressure correction."""

        # Outlets
        bottom = inlets.bottom
        start, end = self._segment_interval()
        wellhead = self.corrected(bottom, self.traverse(bottom, start, end, "up"))

        outlets = dict(wellhead=wellhead)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        bottom = inlets.bottom
        wellhead = outlets.wellhead
        start, end = self._segment_interval()
        result = self.traverse(bottom, start, end, "up")
        self.wellhead_pressure = wellhead.p
        self.wellhead_temperature = wellhead.T
        self.friction_pressure_drop = result.friction_pressure_drop
        self.gravity_pressure_drop = result.gravity_pressure_drop
        self.section_pressure = result.section_pressure
        self.section_temperature = result.section_temperature
        capacity_rate = fluid.heat_capacity_rate(
            wellhead.m_dot, bottom.fluid.properties(bottom.p, bottom.T).cp_l
        )
        self.heat_loss = heat_transfer.heat_rate(capacity_rate, bottom.T - wellhead.T)

    def intake_conditions(self, bottom_stream):
        """Traverse from the sandface to ESP intake, returning a stream in SI units."""
        result = self.traverse(bottom_stream, self.pipe_path.total_length, self._esp_depth(), "up")
        return self.corrected(bottom_stream, result)

    def wellhead_from_discharge(self, discharge_stream):
        """Traverse from ESP discharge to wellhead, returning a stream in SI units."""
        result = self.traverse(discharge_stream, self._esp_depth(), 0, "up")
        return self.corrected(discharge_stream, result)

    def discharge_from_wellhead(self, wellhead_stream):
        """Infer ESP discharge from measured wellhead conditions using downward traversal."""
        result = self.traverse(wellhead_stream, 0, self._esp_depth(), "down")
        return self.corrected(wellhead_stream, result)

    def _segment_interval(self):
        """Return the measured-depth interval [m] the selected segment traverses upward."""
        if self.segment == "below_esp":
            return self.pipe_path.total_length, self._esp_depth()
        if self.segment == "above_esp":
            return self._esp_depth(), 0
        return self.pipe_path.total_length, 0

    def _esp_depth(self):
        depth = self.esp_depth
        if depth is None or depth > self.pipe_path.total_length:
            raise ValidationError(
                f"{self.path}: esp_depth = {depth} m is not configured within the "
                f"{self.pipe_path.total_length} m path",
                code="invalid_design",
            )
        return depth
