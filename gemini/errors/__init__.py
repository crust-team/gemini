"""Every GEMINI exception and warning class, available as ``gm.errors.<Name>``.

Each class also derives from the matching built-in exception, so ``except ValueError`` keeps
catching, for example, ``gm.errors.UnitError``. Nothing in this package imports from the rest
of ``gemini``.
"""

from gemini.errors.base import GeminiError, GeminiWarning
from gemini.errors.engine import (
    BindingError,
    CheckpointError,
    ClockError,
    DatasetError,
    MissingMeasurementError,
    PlantFormatError,
    StepError,
    UnknownResultError,
)
from gemini.errors.legacy import LegacyFormatError
from gemini.errors.module import (
    CallError,
    ConfigurationError,
    DeclarationError,
    FormulaError,
    MissingValueError,
    OutletError,
    OutputError,
    TraceError,
    UnknownMemberError,
    UnknownNameError,
    UnknownPortError,
)
from gemini.errors.physics import (
    InsufficientDataError,
    MissingChemistryError,
    PhysicsRangeError,
    UnitError,
    UnknownCorrelationError,
)

__all__ = [
    "GeminiError",
    "GeminiWarning",
    "DeclarationError",
    "UnknownNameError",
    "UnknownPortError",
    "UnknownMemberError",
    "CallError",
    "OutletError",
    "MissingValueError",
    "OutputError",
    "FormulaError",
    "TraceError",
    "ConfigurationError",
    "DatasetError",
    "ClockError",
    "BindingError",
    "MissingMeasurementError",
    "StepError",
    "CheckpointError",
    "PlantFormatError",
    "UnknownResultError",
    "UnitError",
    "PhysicsRangeError",
    "UnknownCorrelationError",
    "MissingChemistryError",
    "InsufficientDataError",
    "LegacyFormatError",
]
