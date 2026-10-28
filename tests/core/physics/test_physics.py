"""Golden regression and physical-limit checks for the shared SI physics API."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from gemini.core.physics import (
    chemistry,
    corrosion,
    erosion,
    fluid,
    geometry,
    heat_transfer,
    hydraulics,
    units,
)
from tests.golden.test_golden import assert_values

GOLDEN = json.loads((Path(__file__).parents[2] / "golden/golden_values.json").read_text())


@pytest.mark.parametrize("name", [k for k in GOLDEN if k.startswith("corrosion_")])
def test_corrosion_golden(name):
    """All six SI correlation boundaries reproduce original unit-based results."""
    case = GOLDEN[name]
    u, p = case["inputs"], case["parameters"]
    actual = corrosion.co2_corrosion_rate(
        p["corrosion_model"],
        fitted=name.endswith("True"),
        temperature=units.c_to_k(u["temperature"]),
        pressure=units.bar_to_pa(u["pressure"]),
        water_flow_rate=u["flow_rate"],
        water_density=u["water_density"],
        water_viscosity=units.cp_to_pas(u["water_viscosity"]),
        diameter=p["diameter"],
        roughness=p["roughness"],
        co2_fraction=u["co2_fraction"],
        bicarb_concentration=units.mgl_to_kgm3(u["bicarb_concentration"]),
        ionic_strength=u["ionic_strength"],
    )
    assert actual == pytest.approx(case["expected"]["corrosion_rate"], rel=1e-9, abs=0)


@pytest.mark.parametrize("model", ["DNV", "OKA", "TULSA", "API"])
def test_erosion_golden(model):
    """SI rate/velocity boundaries preserve original erosion results."""
    case = GOLDEN["erosion_" + model]
    if model == "API":
        result = erosion.api_erosional_velocity(1068)
        expected = case["expected"]["erosion_velocity_ms"]
    else:
        result = erosion.erosion_rate(
            model, flow_rate=units.m3h_to_m3s(150), rho_fluid=1068, diameter=0.1778
        )
        expected = case["expected"]["erosion_rate_mm_yr"]
    assert result == pytest.approx(expected, rel=1e-9, abs=0)


def test_chemistry_golden():
    """CO2 partition calculation preserves the original partial pressure."""
    value = chemistry.co2_partial_pressure(
        co2_fraction=0.1882,
        gas_pressure=units.bar_to_pa(1),
        gas_water_ratio=0.4224,
        gas_density=1.027,
        gas_molecular_weight=0.022955,
        temperature_sample=units.c_to_k(20),
        temperature_system=units.c_to_k(85),
    )
    assert value == pytest.approx(
        units.bar_to_pa(GOLDEN["chemistry"]["expected"]["CO2 Partial Pressure [bar]"]), rel=1e-9
    )


@pytest.mark.parametrize("role", ["production", "injection"])
def test_path_golden(role):
    """Path marching preserves every original section pressure and temperature."""
    case = GOLDEN["well_" + role]
    p = case["parameters"]
    u = case["inputs"]
    path = geometry.PipePath(
        sections=[
            geometry.PipeSection(length=length, inclination=a, inner_diameter=d, roughness=r)
            for length, a, d, r in zip(p["length"], p["angle"], p["diameter"], p["roughness"])
        ]
    )
    stream = SimpleNamespace(m_dot=u["flowrate"] * 1000, p=u["pressure"], T=u["temperature"])
    result = hydraulics.pipe_path_profile(
        path, stream, fluid.ConstantWater(), u["direction"], 10, u["temperature_ambient"]
    )
    assert_values(
        dict(
            pressure_output=result.p_out,
            temperature_output=result.T_out,
            pressuredrop_fric_output=result.dp_fric,
            pressuredrop_grav_output=result.dp_grav,
            section_pressure_output=result.section_p,
            section_temperature_output=result.section_T,
        ),
        case["expected"],
    )


def test_heat_balance_and_limits():
    """Pipe energy loss and exchanger effectiveness respect limiting cases."""
    change = heat_transfer.pipe_temperature_change(350, 10, 20, 40, 0, 4200, 800, 300)
    assert change * 40 * 4200 == pytest.approx(10 * 20 * 50)
    assert heat_transfer.pipe_temperature_change(300, 10, 20, 40, 0, 4200, 800, 300) == 0
    assert heat_transfer.effectiveness_counterflow(1e6, 0.5) == 1
    assert heat_transfer.effectiveness_counterflow(1, 1) == 0.5
    assert heat_transfer.effectiveness_counterflow(float("inf"), 1) == 1
    assert heat_transfer.effectiveness_parallel(1e6, 1) == 0.5
    assert heat_transfer.lmtd(10, 10) == 10
    with pytest.raises(ValueError):
        heat_transfer.lmtd(10, -1)


def test_wall_loss():
    """WIMS integration uses interval duration and the original 365.25-day year."""
    np.testing.assert_allclose(
        corrosion.wall_loss([1, 2], [units.SECONDS_PER_YEAR / 2] * 2), [0.5, 1.5]
    )


def test_geometry_slice_and_fluid_overrides():
    """Measured-depth slicing conserves length and preserves property overrides."""
    data = Path(__file__).parents[3] / "datasets/geothermal_example"
    path = geometry.build_path(geometry.load_trajectory_csv(data / "well_trajectory.csv"))
    assert path.total_length == 2800
    assert path.subpath(600, 2800).total_length + path.subpath(0, 600).total_length == 2800
    assert geometry.esp_section_index(path, 600) == 2
    assert fluid.ConstantWater(RHOL=1068).properties(1e5, 300).rho_l == 1068
    with pytest.raises(ValueError):
        fluid.get_fluid("unknown")
