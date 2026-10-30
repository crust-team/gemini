"""Capture the unmodified GEMINI model outputs before the package migration.

Historical generator of ``golden_values.json``, committed in a13473d. It ran once with
``PYTHONPATH=src python tests/fixtures/capture_golden.py`` while the original ``gemini_model``
package lived under ``src``; that package is no longer installed, so it cannot run today. It is
kept as the provenance of the immutable JSON: tests compare against that file and must never
regenerate it from the new API.
"""

import json
from pathlib import Path

import numpy as np
from gemini_model.corrosion.co2_corrosion import CO2Corrosion
from gemini_model.corrosion.co2_corrosion_opt import CO2CorrosionOpt
from gemini_model.corrosion.correlation.co2_partial_pressure_model import CO2PartialPressureModel
from gemini_model.erosion.erosion_model import ErosionModel
from gemini_model.fluid.pvt_water_stp import PVTConstantSTP
from gemini_model.pump.esp import ESP
from gemini_model.reservoir.inflow_performance import IPR
from gemini_model.reservoir.injectivity_index import injectivity_index
from gemini_model.reservoir.reservoir_pressure_estimation import reservoir_pressure
from gemini_model.reservoir.reservoir_pressuredrop import bottomhole_skin_dp
from gemini_model.well.correlation.beggsbrill import BeggsBrill
from gemini_model.well.correlation.darcyweisbach import DarcyWeisbach
from gemini_model.well.correlation.temperaturedrop import TemperatureDrop
from gemini_model.well.pressure_drop import DPDT

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "examples/legacy/gemini_project_bridge/old_project"
ESP_POWER_COEFFICIENTS = [10.02089977, -0.000160233, 6.52e-8, -2.13e-12, 1.71e-17, 1.38e-23]
CORROSION_FITS = (
    ("NORSOK", {"A": 1}),
    ("DLM", {"A": 5.8, "B": 1710, "C": 0.67}),
    ("DLD", {"A": 4.93, "B": 1119, "C": 0.58, "D": 2.45}),
)
CORROSION_INPUTS = {
    "co2_fraction": 0.1,
    "pressure": 3,
    "temperature": 40,
    "water_density": 1024,
    "water_viscosity": 0.5469,
    "water_flow_rate": 1000,
    "flow_rate": 1000 / 86400,
    "bicarb_concentration": 268,
    "ionic_strength": 71,
}
EROSION_INPUTS = {
    "alpha": 90,
    "mater": "steel",
    "rho_fluid": 1068,
    "diameter": 0.1778,
    "flowRate": 150,
    "Hv": 1,
    "mater_particle": "SIO2",
    "diameter_particle": 0.1,
    "rho_pipe": 7800,
    "fs": 0.5,
}


def property_block(name):
    """Read the first timestamp of an example property block."""
    return {
        k: v[0] for k, v in json.loads((DATA / name).read_text())["parameters"]["property"].items()
    }


def calculate(cls, parameters, inputs):
    """Evaluate an original model without modifying its implementation."""
    model = cls()
    model.update_parameters(parameters)
    model.calculate_output(inputs, None)
    return model.get_output()


def case(cls, parameters, inputs):
    """Return one case: its fixed parameters and inputs and the original model's result."""
    return {
        "parameters": parameters,
        "inputs": inputs,
        "expected": calculate(cls, parameters, inputs),
    }


def esp_cases():
    """Return the example ESP at three operating points plus a nonzero-power case.

    The nonzero-power case supplements the example's all-zero power coefficients.
    """
    block = property_block("esp_1ee3.param")
    params = {
        "stage_count": block["esp_no_stage"],
        "head_coefficients": list(map(float, block["esp_head_coeff"].split(";"))),
        "power_coefficients": list(map(float, block["esp_power_coeff"].split(";"))),
    }
    cases = {
        f"esp_{frequency}": case(ESP, params, {"pump_flow": flow / 3600, "pump_freq": frequency})
        for flow, frequency in [(90, 40), (130, 50), (170, 60)]
    }
    cases["esp_power"] = case(
        ESP,
        dict(params, power_coefficients=ESP_POWER_COEFFICIENTS),
        {"pump_flow": 130 / 3600, "pump_freq": 60},
    )
    return cases


def inflow_cases():
    """Return the production and injection inflow performance cases."""
    return {
        f"ipr_{role}": case(
            IPR,
            {
                "type": f"{role}_reservoir",
                "reservoir_pressure": 22e6,
                "productivity_index": 21 / 3600 / 1e5,
                "injectivity_index": 20 / 3600 / 1e5,
            },
            {"flow": 150 / 3600},
        )
        for role in ["production", "injection"]
    }


def reservoir_cases():
    """Return the injectivity, reservoir pressure estimation and skin pressure-drop cases."""
    return {
        "injectivity": case(
            injectivity_index,
            {"reservoir_pressure": 22e6},
            {"flow": 150 / 3600, "bottomhole_pressure": 23e6},
        ),
        "reservoir_estimate": case(
            reservoir_pressure,
            {},
            {
                "flow": np.array([0.01, 0.02, 0.03, 0.04]),
                "bottomhole_pressure": np.array([22.5e6, 23e6, 23.5e6, 24e6]),
            },
        ),
        "reservoir_dp": case(
            bottomhole_skin_dp,
            {
                "reservoir_pressure": 22e6,
                "reservoir_radius": 1000,
                "reservoir_permeability": 10000 * 9.869233e-16,
                "reservoir_thickness": 45,
                "reservoir_top": 1800,
            },
            {
                "flow": 150 / 3600,
                "viscosity": 0.00065,
                "density": 1068,
                "well_radius": 0.0765,
                "skin_factor": 2,
            },
        ),
    }


def well_case(role, name, direction, flow, pressure):
    """Return one well pressure-temperature march over the example trajectory."""
    table = property_block(name)[f"{role}well_trajectory_table"]
    length = np.diff([r["MD"] for r in table])
    tvd = np.diff([r["TVD"] for r in table])
    parameters = {
        "length": length,
        "angle": np.round(90 - np.arccos(tvd / length) * 180 / np.pi, 2) * np.pi / 180,
        "diameter": np.array([r["ID"] for r in table[1:]]),
        "roughness": [r["roughness"] for r in table[1:]],
        "friction_correlation": "darcy_weisbach",
        "two_phase_friction_correlation": "BeggsBrill",
        "correction_factors": [1, 0],
    }
    inputs = {
        "flowrate": flow,
        "pressure": pressure,
        "temperature": 353.15,
        "temperature_ambient": 288.15,
        "direction": direction,
    }
    model = DPDT()
    model.PVT = PVTConstantSTP()
    model.update_parameters(parameters)
    model.calculate_output(inputs, None)
    return {"parameters": parameters, "inputs": inputs, "expected": model.get_output()}


def well_cases():
    """Return the production and injection well marches."""
    return {
        f"well_{role}": well_case(role, name, direction, flow, pressure)
        for role, name, direction, flow, pressure in [
            ("production", "production_well_c774.param", "up", 150 / 3600, 25e6),
            ("injection", "injection_well_a06b.param", "down", -150 / 3600, 5e6),
        ]
    }


def correlation_cases():
    """Return the Darcy-Weisbach, Beggs-Brill and pipe temperature-drop correlations."""
    cases = {}
    for name, cls, inputs in [
        ("darcy", DarcyWeisbach, [2, 1000, 1.2, 0.001, 0.1778, 2e-5, 100]),
        (
            "beggs",
            BeggsBrill,
            [0.5, 2, 1.976, 1000, 0.7, 21.29e-6, 0.001, 0.0728, 0.1778, 2e-5, 100],
        ),
        ("temperature", TemperatureDrop, [353.15, 10, 40, 0, 4217.4, 819, 50, 288.15]),
    ]:
        method = cls.calculate_dt if name == "temperature" else cls.calculate_dp
        cases[name] = {"inputs": inputs, "expected": method(*inputs)}
    return cases


def corrosion_cases():
    """Return each CO2 corrosion model with default and fitted coefficients."""
    return {
        f"corrosion_{model}_{fitted}": case(
            cls,
            dict(corrosion_model=model, diameter=0.1, roughness=50e-6, **(fit if fitted else {})),
            dict(CORROSION_INPUTS),
        )
        for fitted, cls in [(False, CO2Corrosion), (True, CO2CorrosionOpt)]
        for model, fit in CORROSION_FITS
    }


def chemistry_cases():
    """Return the CO2 partial-pressure partition case."""
    inputs = {
        "co2_mol_fraction": 0.1882,
        "gas_pressure": 1,
        "gas_water_ratio": 0.4224,
        "gas_density": 1.027,
        "gas_molecular_weight": 22.955,
        "temperature_sample": 20,
        "temperature_system": 85,
    }
    return {"chemistry": case(CO2PartialPressureModel, {}, inputs)}


def erosion_cases():
    """Return each erosion model for the same steel pipe and sand particle."""
    return {
        f"erosion_{model}": case(ErosionModel, {"erosion_model": model}, dict(EROSION_INPUTS))
        for model in ["DNV", "OKA", "TULSA", "API"]
    }


def capture():
    """Return fixed inputs, parameters and original results for every physics family."""
    return (
        esp_cases()
        | inflow_cases()
        | reservoir_cases()
        | well_cases()
        | correlation_cases()
        | corrosion_cases()
        | chemistry_cases()
        | erosion_cases()
    )


if __name__ == "__main__":
    output = Path(__file__).with_name("golden_values.json")
    output.write_text(json.dumps(capture(), indent=2, default=lambda x: x.tolist()) + "\n")
