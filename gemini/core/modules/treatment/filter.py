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

NOMINAL_MASS_FLOW = 149 / 3600 * 1068
"""Default clean-filter design flow [kg/s]: 149 m3/h of brine at 1068 kg/m3.

NOTE(refactor): nominal clean loss from the example (0.016 bar at 149 m3/h).
"""


class Filter(Module):
    """Filter with a quadratic clean-filter pressure loss and a clogging alarm.

    Solids removal itself is not modelled.
    """

    def __init__(self):
        """Declare filter design data, inlet and computed pressure drop."""
        super().__init__()

        # Parameters
        self.dp_nominal = Parameter(PressureDifference, default=1600, ge=0)
        self.m_dot_nominal = Parameter(MassFlow, default=NOMINAL_MASS_FLOW, gt=0)
        self.clogging_dp = Parameter(PressureDifference, default=units.bar_to_pa(0.5), gt=0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.pressure_drop = Output(PressureDifference, soft_sensor=True)

        # Outlets
        self.outlet = Outlet(Stream)

    def forward(self, inlets):
        """Apply a quadratic clean-filter pressure loss."""

        # Outlets
        inlet = inlets.inlet
        outlet = inlet.with_(p=inlet.p - self._pressure_drop(inlet))

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        self.pressure_drop = self._pressure_drop(inlets.inlet)

    def health(self, result, measured):
        """Alarm when measured filter pressure loss exceeds the clogging limit."""
        if "pressure_drop" not in measured:
            return None
        dp = measured["pressure_drop"]
        ratio = max(0, dp) / self.clogging_dp
        alarm = dp > self.clogging_dp
        return Health(
            score=max(0, 1 - ratio),
            alarm=alarm,
            message=(
                "Filter pressure drop exceeds limit"
                if alarm
                else "Filter pressure drop within limit"
            ),
            metrics={"pressure_drop": dp},
        )

    def _pressure_drop(self, inlet):
        """Return the clean-filter loss [Pa], quadratic in mass flow."""
        return self.dp_nominal * (inlet.m_dot / self.m_dot_nominal) ** 2
