"""Scale or corrosion inhibitor injection at a commanded mass dose."""

from gemini import ops
from gemini.errors import PhysicsError
from gemini.modules.module import Module
from gemini.physics import separation
from gemini.types import Control, Fraction, Inlet, MassFlow, Outlet, Output, Parameter, Stream


class InhibitorDosing(Module):
    """Scale or corrosion inhibitor injection proportional to the treated mass flow.

    The dose is the commanded mass of product per mass of treated fluid, the usual field basis
    of inhibitor programmes (mg/kg, written ppm; accepted at the API as ``"10 ppm"``). Typical
    geothermal scale-inhibitor doses are a few to some tens of ppm of product (Gallup, 2009,
    "Production engineering in geothermal technology: A review", *Geothermics* 38, 326-334):

    - ``product_mass_flow = dose * inlet.m_dot``;
    - ``active_mass_flow = product_concentration * product_mass_flow``.

    The dosed product is not added to the stream: at ppm doses it changes the mass flow by less
    than any flowmeter resolves, and adding it would need a product inlet stream to keep the
    mass balance closed. The stream therefore passes unchanged (mass, temperature, pressure and
    fluid) and ``mass_balance`` closes exactly; the neglected mass is ``product_mass_flow``,
    a relative error equal to ``dose``. Dosing-pump power and injection-quill pressure loss are
    neglected. Cost is not modelled; multiply ``product_mass_flow`` by the product price.
    Reverse flow raises ``PhysicsError``.
    """

    def __init__(self):
        """Declare the product strength, ports, dose command and dosing rates."""
        super().__init__()

        # Parameters
        self.product_concentration = Parameter(Fraction, gt=0)

        # Inlets
        self.inlet = Inlet(Stream, stream="brine")

        # Controls
        self.dose = Control(Fraction)

        # Outputs
        self.product_mass_flow = Output(MassFlow)
        self.active_mass_flow = Output(MassFlow)

        # Outlets
        self.outlet = Outlet(Stream, stream="brine")

    def forward(self, inlets):
        """Pass the treated stream through unchanged."""

        # Outlets
        inlet = inlets.inlet
        ops.check(
            inlet.m_dot >= 0,
            PhysicsError,
            "{path}: inlet.m_dot = {m_dot} kg/s; expected >= 0",
            path=self.path,
            m_dot=inlet.m_dot,
        )
        outlet = inlet

        outlets = dict(outlet=outlet)
        return outlets

    def _compute_outputs(self, inlets, outlets):
        product, active = separation.dosing_flows(
            self.dose, inlets.inlet.m_dot, self.product_concentration
        )
        self.product_mass_flow = product
        self.active_mass_flow = active
