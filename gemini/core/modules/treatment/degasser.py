"""Liquid-only degasser with an explicit pressure loss and zero gas flow."""

from gemini.core.modules.module import Module
from gemini.core.types import (
    Inlet,
    MassFlow,
    Outlet,
    Output,
    Parameter,
    Pressure,
    PressureDifference,
    Stream,
)


class Degasser(Module):
    """Separates released gas from the produced geothermal brine."""

    fidelity = "passthrough"

    def __init__(self):
        """Declare degasser design data, inlet and split outlets."""
        super().__init__()

        # Parameters
        self.p_out = Parameter(Pressure | None, default=None)
        self.dp = Parameter(PressureDifference, default=14900, ge=0)
        self.heat_transfer_coeff = Parameter(float, default=0, ge=0)

        # Inlets
        self.inlet = Inlet(Stream)

        # Outputs
        self.gas_mass_flow = Output(MassFlow, soft_sensor=True)
        self.pressure_drop = Output(PressureDifference, soft_sensor=True)

        # Outlets
        self.liquid = Outlet(Stream)
        self.gas = Outlet(Stream)

    def forward(self, inlet):
        """Pass liquid through; gas separation is not modelled and gas flow is zero."""
        # NOTE(refactor): 0.149 bar default loss comes from Sep_Pin/Sep_Pout in the example.
        pressure = self.p_out if self.p_out is not None else inlet.p - self.dp
        liquid = inlet.with_(p=pressure)
        self.gas_mass_flow = 0
        self.pressure_drop = inlet.p - pressure
        return {"liquid": liquid, "gas": liquid.with_(m_dot=0)}
