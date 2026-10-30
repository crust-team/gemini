"""Clean-filter quadratic hydraulic loss and clogging diagnostics."""

from gemini import ops
from gemini.modules.module import Module
from gemini.physics import diagnostics, hydraulics, separation, units
from gemini.types import (
    Health,
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    PressureDifference,
    Stream,
)

DEFAULT_CLOGGING_BAR = separation.FILTER_CLOGGING_BAR
"""Alias of ``separation.FILTER_CLOGGING_BAR``, read by the legacy table converter."""


class Filter(Module):
    """Filter with a quadratic clean-filter pressure loss and a clogging alarm.

    Solids removal itself is not modelled.
    """

    def __init__(self):
        """Declare filter design data, inlet and computed pressure drop."""
        super().__init__()

        # Parameters
        self.dp_nominal = Parameter(
            PressureDifference, default=separation.FILTER_NOMINAL_DROP, ge=0
        )
        self.m_dot_nominal = Parameter(MassFlow, default=separation.FILTER_NOMINAL_MASS_FLOW, gt=0)
        self.clogging_dp = Parameter(
            PressureDifference, default=units.bar_to_pa(separation.FILTER_CLOGGING_BAR), gt=0
        )

        # Inlets
        self.inlet = Inlet(Stream, stream="brine")

        # Outputs
        self.pressure_drop = Output(PressureDifference, soft_sensor=True)

        # Outlets
        self.outlet = Outlet(Stream, stream="brine")

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
        ratio = hydraulics.performance_ratio(ops.maximum(0, dp), self.clogging_dp)
        alarm = dp > self.clogging_dp
        return Health(
            score=diagnostics.remaining_margin(ratio),
            alarm=alarm,
            message=ops.where(
                alarm, "Filter pressure drop exceeds limit", "Filter pressure drop within limit"
            ),
            metrics={"pressure_drop": dp},
        )

    def _pressure_drop(self, inlet):
        """Return the clean-filter loss [Pa], quadratic in mass flow."""
        return hydraulics.quadratic_pressure_drop(self.dp_nominal, inlet.m_dot, self.m_dot_nominal)
