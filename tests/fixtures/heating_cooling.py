"""Stated assumptions to run the heating and cooling template once.

The template ships without values. These are assumptions of the test run, not defaults: the
doublet, degasser, heat exchanger and injection pump take the ``doublet_heat`` example values; the
others take the examples in ``.claude/docs/equipment.md``; flows, temperatures and demands are
round numbers chosen so that every unit runs.
"""

import pandas as pd

import gemini as gm

SIZES = {
    "heat_exchanger.thermal_conductance": 1e5,
    "heat_pump.capacity": 2e6,
    "peak_boiler.capacity": 15e6,
    "peak_boiler.efficiency": 0.9,
    "absorption_chiller.capacity": 3e5,
    "adsorption_chiller.capacity": 1e5,
    "compression_chiller.capacity": 5e5,
    "heating_consumer.return_temperature": 294.85,
    "heating_consumer.return_pressure": 5e5,
    "cooling_consumer.return_temperature": 285.15,
    "cooling_consumer.return_pressure": 5e5,
    "cooling_consumer.dew_point_margin": 3.0,
    **{
        f"{cooler}.{name}": value
        for cooler in ("absorption_cooler", "adsorption_cooler", "compression_cooler")
        for name, value in (
            ("capacity", 1e7),
            ("approach", 5.0),
            ("specific_fan_power", 0.02),
            ("loop_pressure", 3e5),
        )
    },
}
"""Template parameters of the run; the pipes are added by ``with_pipes``."""

CHILLER_FIT = dict(
    characteristic_slope=20000,
    minimum_driving_difference=10,
    rejection_coefficient=2.2,
    evaporator_coefficient=1.2,
    auxiliary_power_ratio=0.01,
)
ADSORPTION_FIT = dict(
    characteristic_slope=2000,
    minimum_driving_difference=5,
    rejection_coefficient=2.0,
    evaporator_coefficient=1.0,
    auxiliary_power_ratio=0.02,
)
PIPE_SIZE = {
    "length": 100.0,
    "inner_diameter": 0.3,
    "elevation_change": 0.0,
    "heat_transfer_coefficient": 0.8,
}
PIPES = ("heating_return_pipe", "heating_supply_pipe", "cooling_return_pipe", "cooling_supply_pipe")
INPUTS = {
    "doublet.reservoir.production_rate": 42.36,
    "doublet.esp.frequency": 55.484,
    "injection_pump.pressure_setpoint": 4568500.0,
    "heat_pump.temperature_setpoint": 353.15,
    "peak_boiler.temperature_setpoint": 358.15,
    "absorption_chiller.temperature_setpoint": 279.15,
    "adsorption_chiller.temperature_setpoint": 283.15,
    "compression_chiller.temperature_setpoint": 281.15,
    "heating_consumer.heat_demand": 1e5,
    "heating_consumer.flow": 48.95,
    "cooling_consumer.flow": 10.0,
    "atmosphere.temperature": 283.15,
    "cooling_consumer.sensible_cooling_demand": 5e4,
    "cooling_consumer.latent_cooling_demand": 1e4,
    "cooling_consumer.indoor_temperature": 297.15,
    "cooling_consumer.indoor_relative_humidity": 0.5,
}
COOLERS = {
    "absorption_cooler": (25.0, 303.15),
    "adsorption_cooler": (10.0, 300.15),
    "compression_cooler": (30.0, 303.15),
}
"""Flow [kg/s] and temperature [K] of the cooling water of each cooler."""
COOLER_INPUTS = {
    f"{cooler}.{name}": value
    for cooler, (flow, temperature) in COOLERS.items()
    for name, value in (("flow", flow), ("temperature_setpoint", temperature))
}
ROOT_STREAMS = {}
BRINE_MODULES = ("doublet", "degasser", "heat_exchanger", "injection_pump")


def filled_dict(name):
    """Return the plant dict of plant class ``name`` with the values of its example."""
    return gm.plants.example(name).to_dict(structure=True)


def configure(plant):
    """Set the remaining parameters, the persisted inputs and the root streams of ``plant``."""
    modules = dict(plant.named_modules())
    for path, fit in {
        "absorption_chiller": CHILLER_FIT,
        "adsorption_chiller": ADSORPTION_FIT,
    }.items():
        if path in modules:
            modules[path].update_params(**fit)
    declared = plant.inputs()
    inputs = INPUTS | COOLER_INPUTS
    plant.set_inputs({path: value for path, value in inputs.items() if path in declared})
    plant.boundary = {"root_inputs": _root_streams(plant)}
    return plant


def _root_streams(plant):
    streams = {}
    for port in plant.inlets():
        flow, temperature = ROOT_STREAMS[port]
        stream = gm.Stream(flow=flow, T=temperature, p="5 bar")
        streams[port] = {"m_dot": stream.m_dot, "T": stream.T, "p": stream.p}
    return streams


def two_ticks():
    """Return a two-row input in the run-input format: only the ticks matter here."""
    index = pd.DatetimeIndex(["2024-07-01T00:00:00Z", "2024-07-01T01:00:00Z"], name="time")
    return gm.Dataset.from_frame(
        pd.DataFrame({"unused": [0.0, 0.0]}, index=index).reset_index(), time_column="time"
    )
