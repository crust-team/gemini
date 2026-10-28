"""Clean-filter quadratic hydraulic loss and clogging diagnostics."""

from gemini.core.modules.module import Module
from gemini.core.physics import units
from gemini.core.types import (
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    PressureDifference,
    Stream,
)
from gemini.core.types.results import Health


class Filter(Module):
    """Removes suspended solids before reinjection into the aquifer."""

    fidelity = "simple"

    def __init__(self):
        """Declare filter design data, inlet and computed pressure drop."""
        super().__init__()

        # Parameters
        # NOTE(refactor): nominal clean loss from the example (0.016 bar at 149 m3/h).
        self.dp_nominal = Parameter(PressureDifference, default=1600, ge=0)
        self.m_dot_nominal = Parameter(MassFlow, default=149 / 3600 * 1068, gt=0)
        self.clogging_dp = Parameter(PressureDifference, default=units.bar_to_pa(0.5), gt=0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.pressure_drop = Output(PressureDifference, soft_sensor=True)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlet):
        """Apply a quadratic clean-filter pressure loss."""

        # Outputs
        self.pressure_drop = self.dp_nominal * (inlet.m_dot / self.m_dot_nominal) ** 2

        # Outlets
        outlet = inlet.with_(p=inlet.p - self.pressure_drop)

        outlets = dict(outlet=outlet)
        return outlets

    def health(self, predicted, measured):
        """Alarm when measured filter pressure loss exceeds the clogging limit."""
        if "pressure_drop" not in measured:
            return None
        dp = measured["pressure_drop"]
        ratio = max(0, dp) / self.clogging_dp
        return Health(
            score=max(0, 1 - ratio),
            alarm=dp > self.clogging_dp,
            message=(
                "Filter pressure drop exceeds limit"
                if dp > self.clogging_dp
                else "Filter pressure drop within limit"
            ),
            metrics={"pressure_drop": dp},
        )
