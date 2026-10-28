"""Preserve historical monitoring numbers through public models, without a legacy runtime."""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import gemini as gm
from gemini.core.engine import registry
from gemini.core.legacy import tables as mapping
from gemini.core.physics import geometry, units
from gemini.core.types.flows import Stream
from tests.unit.test_golden import assert_values

ROOT = Path(__file__).parents[2]
DATA = ROOT / "examples/legacy/gemini_project_bridge/old_project"


def test_captured_monitoring_values():
    """Reproduce all eight immutable historical outputs, including documented arithmetic quirks."""
    row = pd.read_csv(DATA / "doublet_2024_old.csv", sep=";").iloc[1]

    def read(name):
        return mapping.read_property(DATA / (name + ".param"))

    w, e, r = read("production_well_c774"), read("esp_1ee3"), read("reservoir_c1b5")
    pump = registry.create("esp", mapping.esp_params_from_gemini(e))
    with gm.runtime.settings(precision="float32"):
        result = pump(
            frequency=row.ESP_freq,
            suction=Stream(
                m_dot=units.m3h_to_m3s(row.Qp) * 1000,
                T=300,
                p=units.bar_to_pa(row.ESP_Pin),
            ),
        ).outputs
    head = float(units.pa_to_bar(np.float32(result.head)))
    actual = {
        "esp_1ee3:esp_theoretical_head.calculated": [head],
        "esp_1ee3:esp_theoretical_power.calculated": [result.power],
        "esp_1ee3:esp_theoretical_outlet_pressure.calculated": [head + row.ESP_Pin],
    }
    # NOTE(refactor): historical IPR interpreted the labelled m3/h/bar value as m3/s/bar.
    params = mapping.production_reservoir_params_from_gemini(r, w)
    params["productivity_index"] = units.m3s_per_bar_to_si(w["productionwell_productivity_index"])
    reservoir = registry.create("production_reservoir", params)
    wp = mapping.productionwell_params_from_gemini(w, esp_property=e)
    table = w["productionwell_trajectory_table"]
    full = geometry.build_path(table)
    # NOTE(refactor): golden-only reconstruction omits the old ESP-crossing interval and
    # uses one vertical tubing segment above the pump. Production graphs use the full path.
    below = [s for row, s in zip(table, full.sections) if row["MD"] >= e["esp_depth"]]
    top = geometry.PipeSection(
        length=e["esp_depth"],
        inclination=math.pi / 2,
        inner_diameter=e["esp_tubing"],
        roughness=table[1]["roughness"],
    )
    wp["pipe_path"] = geometry.PipePath(sections=[top, *below])
    well = registry.create("production_well", wp)
    well.fluid = reservoir.fluid
    mass = (
        units.m3h_to_m3s(row.Qp)
        * reservoir.fluid.properties(params["pressure"], params["temperature"]).rho_l
    )
    sandface = reservoir(m_dot=mass).outlets["sandface"]
    intake = well.intake_conditions(sandface)
    discharge = well.discharge_from_wellhead(
        Stream(
            m_dot=mass,
            p=units.bar_to_pa(row.Pwh_prod),
            T=units.c_to_k(row.T_p_in),
            fluid=well.fluid,
        )
    )
    a, b = mapping.esp_params_from_gemini(e)["correction_factor"]
    dp = units.pa_to_bar(a * discharge.p + b)
    actual.update(
        {
            "esp_1ee3:esp_vlp_ipr_inlet_pressure.calculated": [units.pa_to_bar(intake.p)],
            "esp_1ee3:esp_vlp_outlet_pressure.calculated": [dp],
            "esp_1ee3:esp_vlp_head.calculated": [dp - row.ESP_Pin],
        }
    )
    w, r = read("injection_well_a06b"), read("reservoir_28fc")
    reservoir = registry.create(
        "injection_reservoir", mapping.injection_reservoir_params_from_gemini(r, w)
    )
    well = registry.create("injection_well", mapping.injectionwell_params_from_gemini(w))
    well.fluid = reservoir.fluid
    p, T = units.bar_to_pa(row.InjectorPump_Pout), units.c_to_k(row.T_p_out)
    stream = Stream(
        m_dot=-units.m3h_to_m3s(row.Qp) * well.fluid.properties(p, T).rho_l,
        p=p,
        T=T,
        fluid=well.fluid,
    )
    out = well(wellhead=stream).outputs
    ii = reservoir.injectivity_from_measurements(units.m3h_to_m3s(row.Qp), out.bottomhole_pressure)
    actual.update(
        {
            "injection_well_a06b:injectionwell_bottomhole_pressure.calculated": [
                units.pa_to_bar(out.bottomhole_pressure)
            ],
            "injection_well_a06b:injectionwell_injectivity_index.calculated": [
                units.index_from_si(ii)
            ],
        }
    )
    assert_values(actual, json.loads((ROOT / "tests/fixtures/runtime_values.json").read_text()))
