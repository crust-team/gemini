"""Electricity exchange of a plant with the public grid through a limited connection."""

from gemini.core.modules.module import Module
from gemini.core.types import Boundary, MoneyPerEnergy, MoneyRate, Output, Parameter, Power


class GridConnection(Module):
    """Grid connection point that nets plant consumption and generation, within limits.

    A parent plant passes its electricity ``consumption`` and ``generation`` as call keywords
    (for example sums of its children's ``electricity`` and ``electricity_generated``). The
    balance consumption - generation is imported when positive and exported when negative,
    each up to its connection limit (``None`` means unlimited). Consumption above the import
    limit is reported as ``unserved_consumption`` (load to shed) and surplus generation above the
    export limit as ``curtailed_generation``. ``cost_rate`` is import_price * net_import -
    export_price * net_export in currency per second; negative values are revenue. Integrating
    it over a step gives the step's electricity cost.

    The module has no ports and deliberately declares none of the six energy outputs audited by
    ``energy_balance``: the plant's consumers and generators already report that energy, so
    repeating it here would count it twice. Assumptions: one tariff per direction, no reactive
    power, losses or demand charges.
    """

    def __init__(self):
        """Declare connection limits, tariffs, plant electricity boundaries and exchange."""
        super().__init__()

        # Parameters
        self.import_limit = Parameter(Power | None, default=None, ge=0)
        self.export_limit = Parameter(Power | None, default=None, ge=0)
        self.import_price = Parameter(MoneyPerEnergy)
        self.export_price = Parameter(MoneyPerEnergy)

        # Boundaries
        self.consumption = Boundary(Power, ge=0)
        self.generation = Boundary(Power, ge=0)

        # Outputs
        self.net_import = Output(Power)
        self.net_export = Output(Power)
        self.unserved_consumption = Output(Power)
        self.curtailed_generation = Output(Power)
        self.is_import_limited = Output(bool)
        self.is_export_limited = Output(bool)
        self.cost_rate = Output(MoneyRate)

    def forward(self, inlets):
        """Exchange electricity only; the connection carries no fluid."""

        outlets = dict()
        return outlets

    def _compute_outputs(self, inlets, outlets):
        demand = max(0.0, self.consumption - self.generation)
        surplus = max(0.0, self.generation - self.consumption)
        self.net_import = _limited(demand, self.import_limit)
        self.net_export = _limited(surplus, self.export_limit)
        self.unserved_consumption = demand - self.net_import
        self.curtailed_generation = surplus - self.net_export
        self.is_import_limited = self.unserved_consumption > 0
        self.is_export_limited = self.curtailed_generation > 0
        self.cost_rate = self.import_price * self.net_import - self.export_price * self.net_export


def _limited(power, limit):
    """Return ``power`` [W] capped at ``limit`` [W]; ``None`` means unlimited."""
    return power if limit is None else min(power, limit)
