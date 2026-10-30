"""CO2 phase-partition checks from the original WEP sample reference."""

import json
from pathlib import Path

import numpy as np
import pytest

from gemini import ops
from gemini.core.physics import chemistry, units
from gemini.graph import Graph
from tests.fixtures.equivalence import RTOL, assert_function_matches
from tests.fixtures.graph_run import graph_outputs

GOLDEN = json.loads((Path(__file__).parents[3] / "fixtures/golden_values.json").read_text())


def test_reference_solubilities():
    """Original mol/l references are expressed as mol/m3 in the new API."""
    assert chemistry.co2_solubility_liquid(0.1882, 293.15, 100000) == pytest.approx(
        7.245, abs=0.001
    )
    assert chemistry.co2_solubility_gas(0.1882, 0.4224, 1.027, 0.022955) == pytest.approx(
        3.557, abs=0.001
    )


def test_henry_constant_reference_and_temperature_dependence():
    """0.0385 mol/l/bar at 293.15 K; solubility falls as temperature rises."""
    assert chemistry.henry_constant(293.15) == pytest.approx(0.0385 * 0.01)
    assert chemistry.henry_constant(350) < chemistry.henry_constant(293.15)


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


def _partial_pressure(fraction, pressure, ratio, density, weight, sample, system):
    return chemistry.co2_partial_pressure(
        co2_fraction=fraction,
        gas_pressure=pressure,
        gas_water_ratio=ratio,
        gas_density=density,
        gas_molecular_weight=weight,
        temperature_sample=sample,
        temperature_system=system,
    )


def test_chemistry_functions_match_on_arrays():
    """Henry constant, both solubilities and the partial pressure agree with the float path."""
    temperatures = [(280.0,), (293.15,), (350.0,)]
    assert_function_matches(chemistry.henry_constant, temperatures)
    assert_function_matches(
        chemistry.co2_solubility_liquid, [(0.1, 293.15, 1e5), (0.5, 330.0, 3e6), (0.0, 300.0, 1e5)]
    )
    assert_function_matches(
        chemistry.co2_solubility_gas, [(0.1882, 0.4224, 1.027, 0.022955), (0.5, 2.0, 1.2, 0.03)]
    )
    assert_function_matches(
        _partial_pressure,
        [
            (0.1882, 1e5, 0.4224, 1.027, 0.022955, 293.15, 358.15),
            (0.5, 2e5, 1.0, 1.2, 0.03, 300.0, 320.0),
        ],
    )


def test_henry_constant_in_a_graph():
    """A traced Henry constant equals the float one on both backends."""
    graph = Graph("henry")
    graph.output("henry", chemistry.henry_constant(graph.input("temperature", "inlet")))
    values = [280.0, 293.15, 350.0]
    traced = graph_outputs(graph, {"temperature": np.array(values)})
    expected = [chemistry.henry_constant(value) for value in values]
    np.testing.assert_allclose(traced["henry"], expected, rtol=RTOL, atol=0)
    assert ops.exp(0.0) == 1.0
