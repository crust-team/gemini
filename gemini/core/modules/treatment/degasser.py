"""Degasser separating a share of the free gas from the liquid, with a pressure loss."""

from gemini.core.modules.module import Module
from gemini.core.types import (
    Fraction,
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
    """Degasser that removes a share of the inlet free gas and applies a pressure loss.

    The inlet free gas is ``fluid.gas_mass_fraction * m_dot``; the share
    ``separation_efficiency`` of it leaves through ``gas``, the rest stays in ``liquid``:

    - ``gas.m_dot = eta * x * inlet.m_dot`` with ``eta = separation_efficiency`` and
      ``x = inlet.fluid.gas_mass_fraction``;
    - ``liquid.m_dot = inlet.m_dot - gas.m_dot``;
    - the liquid gas mass fraction is ``(1 - eta) * x / (1 - eta * x)``, so the free gas left
      in the liquid is conserved.

    Both outlets leave at the vessel pressure, ``p_out`` when set, otherwise ``dp`` below the
    inlet pressure, and at the inlet temperature: no dissolved-gas exsolution, no latent or
    expansion heat. ``separation_efficiency`` is a lumped vessel performance figure; residence
    time, level and gas solubility (Henry's law) are not modelled, so dissolved CO2 stays in the
    liquid. Reverse flow scales both outlets, because the split is linear in mass flow.

    The ``gas`` stream's ``m_dot`` is the separated gas mass flow at vessel pressure and
    temperature. Its ``fluid`` is the liquid outlet's fluid, so its liquid properties do not
    describe the gas: downstream gas equipment uses its own gas properties (or ``rho_g`` and
    ``cp_g`` of ``FluidProperties``). The sensible audit values every stream at ``cp_l``, which
    the degasser therefore closes exactly; the gas enthalpy at ``cp_l`` is an audit convention.

    NOTE(refactor): ``separation_efficiency`` is structural: it sets the gas fraction of the liquid
    outlet's ``Fluid``, which is static during a trace, so a trace reads it as a plain number.
    NOTE(refactor): the 0.149 bar default loss comes from Sep_Pin/Sep_Pout in the example.
    NOTE(refactor): the default ``separation_efficiency = 0`` reproduces the former liquid-only
    model exactly for every fluid (zero gas flow, liquid unchanged but for the pressure loss);
    the example brine carries no free gas either. Separation efficiency is vessel specific and has
    no industry-typical value; set it from design data or a measured gas flow.
    """

    def __init__(self):
        """Declare degasser design data, inlet and split outlets."""
        super().__init__()

        # Parameters
        self.p_out = Parameter(Pressure | None, default=None)
        self.dp = Parameter(PressureDifference, default=14900, ge=0)
        self.heat_transfer_coeff = Parameter(float, default=0, ge=0)
        self.separation_efficiency = Parameter(Fraction, default=0, structural=True)

        # Inlets
        self.inlet = Inlet(Stream, stream="brine")

        # Outputs
        self.gas_mass_flow = Output(MassFlow, soft_sensor=True)
        self.pressure_drop = Output(PressureDifference, soft_sensor=True)

        # Outlets
        self.liquid = Outlet(Stream, stream="brine")
        self.gas = Outlet(Stream, stream="gas")

    def forward(self, inlets):
        """Split the separated free gas from the liquid at the vessel pressure."""

        # Outlets
        inlet = inlets.inlet
        pressure = self.p_out if self.p_out is not None else inlet.p - self.dp
        efficiency = self.separation_efficiency
        fraction = inlet.fluid.gas_mass_fraction
        gas_flow = efficiency * fraction * inlet.m_dot
        remaining = (1 - efficiency) * fraction / (1 - efficiency * fraction)
        fluid = inlet.fluid.model_copy(update={"gas_mass_fraction": remaining})
        liquid = inlet.with_(m_dot=inlet.m_dot - gas_flow, p=pressure, fluid=fluid)
        gas = liquid.with_(m_dot=gas_flow)

        outlets = dict(liquid=liquid, gas=gas)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        inlet = inlets.inlet
        liquid = outlets.liquid
        gas = outlets.gas
        self.gas_mass_flow = gas.m_dot
        self.pressure_drop = inlet.p - liquid.p
