"""The gas grid as a source and the mark of the makeup."""

import pytest

import gemini as gm
from gemini.modules import GasGrid, GasMakeup
from gemini.physics import gas
from tests.fixtures.equivalence import assert_module_matches

FLUID = gm.Fluid(kind="gas", gas_composition={"CH4": 0.8, "CO2": 0.2})
GAS = gm.Stream(m_dot=0.05, T=330, p=2e5, fluid=FLUID)


def test_the_grid_is_a_marked_source_without_flow():
    """Purchased gas enters no stream; the stream says the burner may draw it."""
    outlet = GasGrid()().outlets.outlet
    assert outlet.m_dot == 0 and outlet.fluid.kind == "gas"
    assert outlet.fluid.grid_composition == gas.GRID_COMPOSITION
    assert outlet.T == gas.NORMAL_TEMPERATURE and outlet.p == gas.NORMAL_PRESSURE


def test_the_composition_is_a_parameter():
    """Another grid gas is one parameter."""
    grid = GasGrid().update_params(composition={"CH4": 1.0})
    assert grid().outlets.outlet.fluid.grid_composition == {"CH4": 1.0}


def test_the_makeup_marks_the_stream_and_moves_no_gas():
    """Mass, temperature, pressure and composition stay."""
    outlet = GasMakeup()(inlet=GAS).outlets.outlet
    assert (outlet.m_dot, outlet.T, outlet.p) == (GAS.m_dot, GAS.T, GAS.p)
    assert outlet.fluid.gas_composition == FLUID.gas_composition
    assert outlet.fluid.grid_composition == gas.GRID_COMPOSITION


def test_traced_calls_match_one_call_per_row():
    """Both trace."""
    assert_module_matches(GasMakeup(), [dict(inlet=GAS.with_(m_dot=flow)) for flow in (0.0, 0.1)])
    assert pytest.approx(0) == GasGrid()().outlets.outlet.m_dot
