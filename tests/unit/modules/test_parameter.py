"""The graph-input roles are the existing declarations plus ``Constant``."""

from gemini.modules import parameter
from gemini.ops import Constant
from gemini.physics import constants
from gemini.types import declarations


def test_roles_reuse_the_existing_declarations():
    """``Parameter`` and ``State`` are the module declarations; ``Constant`` is the op operand."""
    assert parameter.Parameter is declarations.Parameter
    assert parameter.State is declarations.State
    assert parameter.Constant is Constant
    assert isinstance(constants.ESP_REFERENCE_FREQUENCY, parameter.Constant)
