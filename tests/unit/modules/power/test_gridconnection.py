"""Grid import/export netting, connection limits, cost rate and use inside a plant."""

import pytest

from gemini.modules import Module, collect_flows, energy_balance
from gemini.modules.heating import ElectricBoiler
from gemini.modules.power import ORC, GridConnection
from gemini.types import Inlet, Outlet, Output, Stream
from tests.fixtures.equivalence import assert_module_matches


def grid(**changes):
    """Return a connection buying at 0.20 and selling at 0.08 currency per kWh."""
    params = dict(import_price="0.2 currency/kWh", export_price="0.08 currency/kWh")
    return GridConnection().update_params(**(params | changes))


def test_import_and_export_within_unlimited_connection():
    """Net consumption is imported at the import price; surplus is sold at the export price."""
    out = grid()(consumption=3e6, generation=1e6).outputs
    assert out.net_import == 2e6 and out.net_export == 0
    assert out.cost_rate == pytest.approx(2e3 * 0.2 / 3600, rel=1e-12)
    assert not out.is_import_limited and out.unserved_consumption == 0
    out = grid()(consumption=1e6, generation=4e6).outputs
    assert out.net_export == 3e6 and out.net_import == 0
    assert out.cost_rate == pytest.approx(-3e3 * 0.08 / 3600, rel=1e-12)


def test_connection_limits():
    """Imports above the limit go unserved; exports above it are curtailed."""
    connection = grid(import_limit="1 MW", export_limit="0.5 MW")
    out = connection(consumption=3e6, generation=1e6).outputs
    assert out.net_import == 1e6 and out.unserved_consumption == 1e6 and out.is_import_limited
    out = connection(consumption=0, generation=2e6).outputs
    assert out.net_export == 5e5 and out.curtailed_generation == 1.5e6 and out.is_export_limited
    out = grid(export_limit=0)(consumption=0, generation=0).outputs
    assert out.cost_rate == 0 and not out.is_export_limited
    assert out.get("cost_rate", unit="currency/h") == 0


class GridPlant(Module):
    """An ORC selling to the grid while an electric boiler buys from it."""

    def __init__(self):
        """Declare the test plant."""
        super().__init__()

        # Modules
        self.orc = ORC().update_params(
            minimum_brine_outlet_temperature=343.15,
            pinch=5,
            carnot_fraction=0.5,
            condenser_approach=15,
            parasitic_fraction=0.15,
            capacity=5e6,
        )
        self.boiler = ElectricBoiler().update_params(capacity=1e6, efficiency=0.99)
        self.grid = grid(export_limit="10 MW")

        # Inlets
        self.fluid_in = Inlet(Stream)
        self.water_in = Inlet(Stream)

        # Outputs
        self.net_export = Output.of(self.grid.net_export)

        # Outlets
        self.fluid_out = Outlet(Stream)
        self.water_out = Outlet(Stream)

    def forward(self, inlets):
        """Generate, consume, then settle with the grid."""

        # Modules
        generated = self.orc(fluid_in=inlets.fluid_in, ambient_temperature=288.15)
        heated = self.boiler(fluid_in=inlets.water_in, temperature_setpoint=353.15)
        self.grid(
            consumption=heated.outputs.electricity,
            generation=generated.outputs.electricity_generated,
        )

        # Outlets
        fluid_out = generated.outlets.fluid_out
        water_out = heated.outlets.fluid_out

        outlets = dict(fluid_out=fluid_out, water_out=water_out)
        return outlets


def test_grid_is_not_counted_in_the_energy_audit():
    """Plant totals keep the ORC and boiler energy once; the grid adds none."""
    plant = GridPlant()
    result = plant(
        fluid_in=Stream(m_dot=100, T=423.15, p=10e5), water_in=Stream(m_dot=5, T=313.15, p=3e5)
    )
    orc, boiler = result.children["orc"].outputs, result.children["boiler"].outputs
    flows = collect_flows(result)
    assert flows["electricity_generated"] == orc.electricity_generated
    assert flows["electricity"] == boiler.electricity
    assert result.outputs.net_export == pytest.approx(
        orc.electricity_generated - boiler.electricity, rel=1e-12
    )
    assert energy_balance(plant, result)["relative_residual"] < 1e-12


class RowCarrier(GridConnection):
    """A connection with a dummy inlet whose length gives the runner its number of rows."""

    def __init__(self):
        """Declare the connection and the row-carrying inlet."""
        super().__init__()
        self.rows = Inlet(Stream)


def test_traced_call_matches_one_call_per_row():
    """Import, export, limited and unlimited rows trace and equal one call per row."""
    rows = [
        dict(rows=Stream(m_dot=1.0, T=300.0, p=1e5), consumption=consumption, generation=generation)
        for consumption, generation in [(3e6, 1e6), (1e6, 4e6), (0.0, 2e6), (5e5, 5e5), (4e6, 0.0)]
    ]
    prices = dict(import_price="0.2 currency/kWh", export_price="0.08 currency/kWh")
    assert_module_matches(RowCarrier().update_params(**prices), rows)
    limited = RowCarrier().update_params(import_limit="1 MW", export_limit="0.5 MW", **prices)
    assert_module_matches(limited, rows)
