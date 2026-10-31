"""The gas grid as a source."""

from gemini.modules import GasGrid
from gemini.physics import gas
from tests.fixtures.equivalence import assert_module_matches

GRID = GasGrid().offer()["gas_out"]


def test_the_grid_is_a_marked_source_without_flow():
    """Purchased gas enters no stream; the stream says the burner may draw it."""
    outlet = GasGrid().offer()["gas_out"]
    assert outlet.m_dot == 0 and outlet.fluid.kind == "gas"
    assert outlet.fluid.grid_composition == gas.GRID_COMPOSITION
    assert outlet.T == gas.NORMAL_TEMPERATURE and outlet.p == gas.NORMAL_PRESSURE


def test_the_composition_is_a_parameter():
    """Another grid gas is one parameter."""
    grid = GasGrid().update_params(composition={"CH4": 1.0})
    assert grid.offer()["gas_out"].fluid.grid_composition == {"CH4": 1.0}


def test_what_the_taker_drew_reaches_the_grid():
    """A plant passes what its taker drew; a direct call takes the offer."""
    result = GasGrid()(gas_out=GRID.with_(m_dot=0.2))
    assert result.outlets.gas_out.m_dot == 0.2
    assert GasGrid()().outlets.gas_out.m_dot == 0


def test_traced_calls_match_one_call_per_row():
    """A grid without a taker traces."""
    assert_module_matches(GasGrid(), [{}, {}])
