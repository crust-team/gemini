"""Graph-input roles: ``Parameter``, ``Constant`` and ``State``.

A data type says what a value is; a role says how a computation graph treats it.
``Parameter`` is calibratable design data (the existing declaration, assigned in ``__init__``);
``Constant`` is fixed by default and can be released for sensitivity studies (defined in
``gemini.ops`` because physics uses it, for example ``physics.constants.ESP_REFERENCE_FREQUENCY``);
``State`` is carried from step to step (the existing declaration). Each numeric parameter and
each constant a traced call uses is one named graph input, never a literal.
"""

from gemini.core.types.declarations import Parameter, State
from gemini.ops import Constant

__all__ = ["Constant", "Parameter", "State"]
