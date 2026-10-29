"""ATES plant: free cooling while charging, heat pump while discharging, steps and balances."""

import pytest

import gemini as gm
from gemini.core.modules import Module, energy_balance, mass_balance
from gemini.core.modules.plants import ATESPlant
from gemini.core.types import Inlet, Outlet, Output, Stream

CP = 4217.4
HOUR = 3600.0
SUMMER = Stream(m_dot=40.0, T=290.15, p=3e5)
WINTER = SUMMER.with_(T=303.15)


def _plant(mode="charge"):
    """Return a 30 kg/s ATES plant with a 1 MW/K exchanger and a 2 MW heat pump."""
    plant = ATESPlant().update_params(groundwater_pressure=3e5)
    plant.groundwater_flow = 30.0
    plant.storage.update_params(
        aquifer_temperature=284.15,
        aquifer_thickness=30,
        porosity=0.3,
        rock_volumetric_heat_capacity=2.0e6,
        ground_conductivity=2.5,
    )
    plant.storage.mode = mode
    plant.pump.update_params(
        head_coeff=[3e5, 0.0, -1e8],
        rated_frequency=50,
        best_efficiency=0.7,
        best_efficiency_flow=0.03,
        motor_efficiency=0.9,
    )
    plant.pump.frequency = 50
    plant.heat_exchanger.update_params(
        ua=1e6, dp_hot_nominal=3e4, dp_cold_nominal=3e4, m_dot_hot_nominal=40, m_dot_cold_nominal=30
    )
    plant.heat_pump.update_params(mode="heating", capacity=2e6)
    plant.heat_pump.temperature_setpoint = 313.15
    return plant


def _check_balances(plant, result):
    """Check that the audit closes except for the pump's flow work and that mass is conserved."""
    audit = energy_balance(plant, result)
    hydraulic = result.children["pump"].outputs.hydraulic_power
    assert abs(audit["residual"] - hydraulic) / audit["in"] < 1e-12
    assert mass_balance(plant, result)["residual"] == 0


def test_charge_cools_the_building_with_native_groundwater():
    """Empty stores produce at the aquifer temperature; the exchanger cools the building."""
    plant = _plant()
    result = plant(building_in=SUMMER)
    out = result.outputs
    exchanger = result.children["heat_exchanger"]
    groundwater = exchanger.inlets.cold_in
    assert out.production_T == 284.15 and groundwater.T > 284.15
    assert result.outlets.building_out == exchanger.outlets.hot_out
    assert result.outlets.building_out.T < SUMMER.T
    storage = result.children["storage"]
    assert storage.inlets.injection_in.T == exchanger.outlets.cold_out.T
    assert storage.inlets.injection_in.p == 3e5
    assert storage.outlets.production_out == result.children["pump"].inlets.suction
    assert "heat_pump" not in result.children
    assert out.heat_accumulation == pytest.approx(
        30.0 * CP * (storage.inlets.injection_in.T - 284.15), rel=1e-9
    )
    _check_balances(plant, result)


def test_two_charge_steps_fill_the_warm_store():
    """Stepping twice fills the warm store with the first hour's accumulation less conduction.

    The conduction loss that sets in during the first hour takes about 0.15 %.
    """
    plant = _plant()
    state, first = plant.step(None, HOUR, {"building_in": SUMMER})
    state, second = plant.step(state, HOUR, {"building_in": SUMMER})
    assert state["storage"]["warm_volume"] == pytest.approx(2 * 30 / 1000 * HOUR)
    assert state["storage"]["warm_temperature_change"] > 0
    assert first.outputs.stored_energy == 0
    stored = first.outputs.heat_accumulation * HOUR
    assert stored > second.outputs.stored_energy > 0.995 * stored
    _check_balances(plant, second)


def test_discharge_feeds_the_heat_pump_from_the_warm_store():
    """After charging, the warm store feeds the evaporator and the condenser heats the building."""
    plant = _plant()
    state, _ = plant.step(None, 6 * HOUR, {"building_in": SUMMER})
    warm = 284.15 + state["storage"]["warm_temperature_change"]
    plant.storage.mode = "discharge"
    state, result = plant.step(state, HOUR, {"building_in": WINTER})
    out = result.outputs
    lifted = result.children["heat_pump"]
    assert out.production_T == pytest.approx(warm, rel=1e-14)
    assert result.children["pump"].inlets.suction.T == out.production_T
    assert result.outlets.building_out.T == pytest.approx(313.15, rel=1e-12)
    assert lifted.inlets.source_in == result.children["pump"].outlets.discharge
    assert result.children["storage"].inlets.injection_in.T == lifted.outlets.source_out.T < warm
    assert "heat_exchanger" not in result.children
    assert out.electricity == pytest.approx(
        lifted.outputs.electricity + result.children["pump"].outputs.electricity, rel=1e-14
    )
    assert state["storage"]["cold_volume"] == pytest.approx(30 / 1000 * HOUR)
    _check_balances(plant, result)


def test_idle_moves_no_groundwater_and_flow_is_required_to_stop():
    """Idle passes the building circuit; idle with groundwater flow raises."""
    plant = _plant("idle")
    plant.groundwater_flow = 0.0
    result = plant(building_in=SUMMER)
    assert result.outlets.building_out.T == SUMMER.T
    assert result.outputs.electricity == 0
    plant.groundwater_flow = 30.0
    with pytest.raises(gm.errors.PhysicsRangeError, match="idle"):
        plant(building_in=SUMMER)


class Campus(Module):
    """Building loop served by the ATES plant, to step it as a child."""

    def __init__(self):
        """Declare the test composite."""
        super().__init__()

        # Modules
        self.ates = _plant()

        # Inlets
        self.return_in = Inlet(Stream)

        # Outputs
        self.stored_energy = Output.of("ates.stored_energy")

        # Outlets
        self.supply_out = Outlet(Stream)

    def forward(self, inlets):
        """Cool the building return."""

        # Modules
        served = self.ates(building_in=inlets.return_in)

        # Outlets
        supply_out = served.outlets.building_out

        outlets = dict(supply_out=supply_out)
        return outlets


def test_nested_plant_steps_through_its_parent():
    """A parent composite steps the ATES storage two levels down."""
    campus = Campus()
    state, _ = campus.step(None, HOUR, {"return_in": SUMMER})
    state, result = campus.step(state, HOUR, {"return_in": SUMMER})
    assert state["ates"]["storage"]["warm_volume"] == pytest.approx(2 * 30 / 1000 * HOUR)
    assert result.outputs.stored_energy > 0
