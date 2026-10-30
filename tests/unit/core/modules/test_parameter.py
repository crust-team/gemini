"""The graph-input roles are the existing declarations plus ``Constant``."""

from gemini.core.modules import parameter
from gemini.core.physics import constants
from gemini.core.types import declarations
from gemini.ops import Constant


def test_roles_reuse_the_existing_declarations():
    """``Parameter`` and ``State`` are the module declarations; ``Constant`` is the op operand."""
    assert parameter.Parameter is declarations.Parameter
    assert parameter.State is declarations.State
    assert parameter.Constant is Constant
    assert isinstance(constants.ESP_REFERENCE_FREQUENCY, parameter.Constant)
