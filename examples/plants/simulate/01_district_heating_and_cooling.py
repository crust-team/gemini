"""Step a small district energy plant: a heating network and an ATES-cooled cooling network.

A geothermal supply feeds a heating network with two building substations. In parallel an
aquifer thermal energy storage (ATES) plant runs in its charge (summer) mode: cold groundwater
chills the water of a cooling network that serves one building, and the warmed groundwater is
stored in the warm well. The cooling network's return is fed back to the ATES plant at the next
step. Each hourly step is checked for energy closure: the sensible-enthalpy audit closes except
for the pumps' flow work.

Run from the repository root:
PYTHONPATH=. python examples/plants/simulate/01_district_heating_and_cooling.py
"""

import gemini as gm
from gemini.modules import ATESPlant, energy_balance
from gemini.types import (
    Electricity,
    HeatAbsorbed,
    HeatSupplied,
    HydraulicPower,
    Inlet,
    Outlet,
    Output,
    Stream,
)

HOUR = 3600.0
GEOTHERMAL_SUPPLY = Stream(flow="18 t/h", T="75 degC", p="6 bar")
FIRST_COOLING_RETURN = Stream(flow="36 t/h", T="17 degC", p="3 bar")


class DistrictEnergyPlant(gm.modules.Module):
    """Heating network on a geothermal supply and a cooling network on an ATES plant."""

    def __init__(self):
        """Build both networks and the ATES plant."""
        super().__init__()

        # Modules
        self.heating = gm.plants.from_template("DistrictNetwork", {"consumers": 2})
        self.ates = ATESPlant()
        self.cooling = gm.plants.from_template(
            "DistrictNetwork", {"consumers": 1, "service": "cooling"}
        )

        # Inlets
        self.heat_supply_in = Inlet(Stream)
        self.cooling_return_in = Inlet(Stream)

        # Outputs
        self.heat_supplied = Output(HeatSupplied)
        self.heat_absorbed = Output(HeatAbsorbed)
        self.electricity = Output(Electricity)
        self.hydraulic_power = Output(HydraulicPower)
        self.stored_energy = Output.of(self.ates.stored_energy)

        # Outlets
        self.heat_return_out = Outlet(Stream)
        self.cooling_return_out = Outlet(Stream)

    def forward(self, inlets):
        """Serve the heating network, chill the cooling water and serve the cooling network."""

        # Modules
        heated = self.heating(supply_in=inlets.heat_supply_in)
        chilled = self.ates(building_in=inlets.cooling_return_in)
        cooled = self.cooling(supply_in=chilled.outlets.building_out)

        # Outlets
        heat_return_out = heated.outlets.return_out
        cooling_return_out = cooled.outlets.return_out

        outlets = dict(heat_return_out=heat_return_out, cooling_return_out=cooling_return_out)
        return outlets


def configure_network(network, design_flow):
    """Fill the circulation pump and the two 400 m DN150 pipes of a network."""
    network.pump.update_params(
        head_coeff=[3e5, 0.0, -1e5 / design_flow**2],
        rated_frequency="50 Hz",
        best_efficiency=0.75,
        best_efficiency_flow=design_flow,
        motor_efficiency=0.92,
    )
    network.pump.frequency = "50 Hz"
    for pipe in (network.supply_pipe, network.return_pipe):
        pipe.update_params(length=400, inner_diameter=0.15, elevation_change=0, u_value=0.8)
        pipe.ambient_temperature = "10 degC"


def configure_substation(substation, ua, network_flow):
    """Fill the valve, exchanger and building circuit shared by both substation types."""
    substation.update_params(building_flow=network_flow * 1.2, building_pressure="3 bar")
    substation.valve.update_params(flow_coefficient="40 m3/h/bar^0.5")
    substation.valve.opening = 0.9
    substation.heat_exchanger.update_params(
        ua=ua,
        dp_hot_nominal="0.2 bar",
        dp_cold_nominal="0.2 bar",
        m_dot_hot_nominal=network_flow,
        m_dot_cold_nominal=network_flow * 1.2,
    )


def configure_heating(network):
    """Fill the heating network: two buildings of 150 and 100 kW with a 30 degC return floor."""
    configure_network(network, design_flow=0.005)
    network.splitters[0].split_fraction = 0.5
    for substation, demand in zip(network.substations, ("150 kW", "100 kW")):
        configure_substation(substation, ua=2.5e4, network_flow=2.5)
        substation.consumer.update_params(minimum_return_temperature="30 degC")
        substation.consumer.heat_demand = demand


def configure_cooling(network):
    """Fill the cooling network: one building with a 150 kW sensible load."""
    configure_network(network, design_flow=0.01)
    substation = network.substations[0]
    configure_substation(substation, ua=1.2e5, network_flow=10.0)
    substation.consumer.update_params(maximum_return_temperature="19 degC", dew_point_margin=1.0)
    substation.set_inputs(
        {
            "consumer.sensible_cooling_demand": "150 kW",
            "consumer.latent_cooling_demand": 0.0,
            "consumer.indoor_temperature": "24 degC",
            "consumer.indoor_relative_humidity": 0.5,
        }
    )


def configure_ates(ates):
    """Fill the ATES plant: 10 kg/s from a 30 m aquifer at 11 degC, charging the warm well."""
    ates.update_params(groundwater_pressure="3 bar")
    ates.groundwater_flow = "36 t/h"
    ates.storage.update_params(
        aquifer_temperature="11 degC",
        aquifer_thickness=30,
        porosity=0.3,
        rock_volumetric_heat_capacity=2.0e6,
        ground_conductivity=2.5,
    )
    ates.storage.mode = "charge"
    ates.pump.update_params(
        head_coeff=[2e5, 0.0, -5e8],
        rated_frequency="50 Hz",
        best_efficiency=0.7,
        best_efficiency_flow=0.01,
        motor_efficiency=0.9,
    )
    ates.pump.frequency = "50 Hz"
    ates.heat_exchanger.update_params(
        ua=4e5,
        dp_hot_nominal="0.3 bar",
        dp_cold_nominal="0.3 bar",
        m_dot_hot_nominal=10,
        m_dot_cold_nominal=10,
    )
    ates.heat_pump.update_params(mode="heating", capacity="1 MW")
    ates.heat_pump.temperature_setpoint = "40 degC"


def build_plant():
    """Return the configured district energy plant."""
    plant = DistrictEnergyPlant()
    configure_heating(plant.heating)
    configure_cooling(plant.cooling)
    configure_ates(plant.ates)
    return plant


def check_closure(plant, result):
    """Assert that the audit residual is the pumps' flow work, within rounding."""
    audit = energy_balance(plant, result)
    unexplained = audit["residual"] - result.outputs.hydraulic_power
    assert abs(unexplained) <= 1e-9 * audit["in"], unexplained
    return audit


def main():
    """Step the plant for six hours and print one line per step."""
    plant = build_plant()
    state, cooling_return = None, FIRST_COOLING_RETURN
    print("hour  heat kW  cold kW  electricity kW  stored MWh  chilled degC")
    for hour in range(6):
        inlets = {"heat_supply_in": GEOTHERMAL_SUPPLY, "cooling_return_in": cooling_return}
        state, result = plant.step(state, HOUR, inlets)
        check_closure(plant, result)
        out = result.outputs
        chilled = result.children["ates"].outlets.building_out.T - 273.15
        print(
            f"{hour:4d} {out.heat_supplied / 1e3:8.1f} {out.heat_absorbed / 1e3:8.1f} "
            f"{out.electricity / 1e3:15.2f} {out.stored_energy / 3.6e9:11.3f} {chilled:13.2f}"
        )
        cooling_return = result.outlets.cooling_return_out


if __name__ == "__main__":
    main()
