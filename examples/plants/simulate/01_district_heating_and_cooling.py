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
from gemini.modules import (
    ATESPlant,
    Atmosphere,
    CoolingGrid,
    ElectricityGrid,
    HeatingGrid,
    collect_flows,
    energy_balance,
)
from gemini.types import (
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

        self.electricity_grid = ElectricityGrid()
        self.air = Atmosphere()

        # Inlets
        self.heat_supply_in = Inlet(Stream)
        self.cooling_return_in = Inlet(Stream)
        self.air_in = Inlet(Stream, kind="air")

        # Outputs
        self.stored_energy = Output.of(self.ates.stored_energy)

        # Outlets
        self.heat_return_out = Outlet(Stream)
        self.cooling_return_out = Outlet(Stream)

    def forward(self, inlets):
        """Serve the heating network, chill the cooling water and serve the cooling network."""

        # Modules
        heated = self.heating(supply_in=inlets.heat_supply_in, air_in=inlets.air_in)
        chilled = self.ates(return_in=inlets.cooling_return_in)
        cooled = self.cooling(supply_in=chilled.outlets.supply_out, air_in=inlets.air_in)
        self.electricity_grid(
            power_in=[],
            power_out=[
                heated.inlets.power_in,
                chilled.inlets.power_in,
                cooled.inlets.power_in,
            ],
        )
        self.air(
            air_in=[],
            gas_in=[],
            heat_in=[
                heated.outlets.loss_out,
                chilled.outlets.loss_out,
                cooled.outlets.loss_out,
            ],
        )

        # Outlets
        heat_return_out = heated.outlets.return_out
        cooling_return_out = cooled.outlets.return_out

        outlets = dict(heat_return_out=heat_return_out, cooling_return_out=cooling_return_out)
        return outlets


def configure_network(network, design_flow):
    """Fill the circulation pump and the two 400 m DN150 pipes of a network."""
    network.pump.update_params(
        head_coefficients=[3e5, 0.0, -1e5 / design_flow**2],
        rated_frequency="50 Hz",
        best_efficiency=0.75,
        best_efficiency_flow=design_flow,
        motor_efficiency=0.92,
    )
    network.pump.frequency = "50 Hz"
    for pipe in (network.supply_pipe, network.return_pipe):
        pipe.update_params(
            length=400, inner_diameter=0.15, elevation_change=0, heat_transfer_coefficient=0.8
        )


def configure_substation(substation, thermal_conductance, network_flow):
    """Fill the valve, exchanger and building circuit shared by both substation types."""
    substation.update_params(building_flow=network_flow * 1.2, building_pressure="3 bar")
    substation.valve.update_params(flow_coefficient="40 m3/h/bar^0.5")
    substation.valve.opening = 0.9
    substation.heat_exchanger.update_params(
        thermal_conductance=thermal_conductance,
        hot_nominal_pressure_drop="0.2 bar",
        cold_nominal_pressure_drop="0.2 bar",
        hot_nominal_mass_flow=network_flow,
        cold_nominal_mass_flow=network_flow * 1.2,
    )


def configure_heating(network):
    """Fill the heating network: two buildings of 150 and 100 kW with a 30 degC return floor."""
    configure_network(network, design_flow=0.005)
    network.splitters[0].split_fraction = 0.5
    for substation, demand in zip(network.substations, ("150 kW", "100 kW")):
        configure_substation(substation, thermal_conductance=2.5e4, network_flow=2.5)
        substation.consumer.update_params(minimum_return_temperature="30 degC")
        substation.consumer.heat_demand = demand


def configure_cooling(network):
    """Fill the cooling network: one building with a 150 kW sensible load."""
    configure_network(network, design_flow=0.01)
    substation = network.substations[0]
    configure_substation(substation, thermal_conductance=1.2e5, network_flow=10.0)
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
        head_coefficients=[2e5, 0.0, -5e8],
        rated_frequency="50 Hz",
        best_efficiency=0.7,
        best_efficiency_flow=0.01,
        motor_efficiency=0.9,
    )
    ates.pump.frequency = "50 Hz"
    ates.heat_exchanger.update_params(
        thermal_conductance=4e5,
        hot_nominal_pressure_drop="0.3 bar",
        cold_nominal_pressure_drop="0.3 bar",
        hot_nominal_mass_flow=10,
        cold_nominal_mass_flow=10,
    )
    ates.heat_pump.update_params(mode="heating", capacity="1 MW")
    ates.heat_pump.temperature_setpoint = "40 degC"


def build_plant():
    """Return the configured district energy plant."""
    plant = DistrictEnergyPlant()
    configure_heating(plant.heating)
    configure_cooling(plant.cooling)
    configure_ates(plant.ates)
    plant.air.temperature = "10 degC"
    return plant


def hydraulic_power(result):
    """Return the flow work [W] of every pump of ``result``."""
    leaves = result.leaves().values()
    return sum(leaf.outputs.get("hydraulic_power", 0.0) for leaf in leaves)


def check_closure(plant, result):
    """Assert that the audit residual is the pumps' flow work, within rounding."""
    audit = energy_balance(plant, result)
    unexplained = audit["residual"] - hydraulic_power(result)
    assert abs(unexplained) <= 1e-9 * audit["in"], unexplained
    return audit


def consumer_heat(plant, result, module_class):
    """Return the heat [W] the water gives up in the leaves of ``module_class``, by their ports."""
    consumers = [
        leaf
        for path, leaf in result.leaves().items()
        if isinstance(plant.get_submodule(path), module_class)
    ]
    return sum(
        leaf.inlets.supply_in.quantities()["enthalpy_flow"]
        - leaf.outlets.return_out.quantities()["enthalpy_flow"]
        for leaf in consumers
    )


def main():
    """Step the plant for six hours and print one line per step."""
    plant = build_plant()
    state, cooling_return = None, FIRST_COOLING_RETURN
    print("hour  heat kW  cold kW  electricity kW  stored MWh  chilled degC")
    for hour in range(6):
        inlets = {
            "heat_supply_in": GEOTHERMAL_SUPPLY,
            "cooling_return_in": cooling_return,
            "air_in": gm.modules.Atmosphere.ambient_air("10 degC"),
        }
        state, result = plant.step(state, HOUR, inlets)
        check_closure(plant, result)
        assert all(check["passed"] for check in gm.checks.plant_balance(plant, result))
        out, flows = result.outputs, collect_flows(result)
        heat = consumer_heat(plant, result, HeatingGrid)
        cold = flows["heat_absorbed"] - consumer_heat(plant, result, CoolingGrid)
        chilled = result.children["ates"].outlets.supply_out.T - 273.15
        print(
            f"{hour:4d} {heat / 1e3:8.1f} {cold / 1e3:8.1f} "
            f"{flows['electricity'] / 1e3:15.2f} {out.stored_energy / 3.6e9:11.3f} {chilled:13.2f}"
        )
        cooling_return = result.outlets.cooling_return_out


if __name__ == "__main__":
    main()
