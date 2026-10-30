"""Errors in datasets, clocks, bindings, runs, results, plant files and checkpoints."""

from gemini.errors import base
from gemini.errors.base import GeminiError


class DatasetError(GeminiError, TypeError, ValueError):
    """A dataset cannot be built from, or read with, the given data."""

    code = "invalid_data"


class ClockError(GeminiError, KeyError, ValueError):
    """A clock is invalid, or a timestamp is not one of its ticks."""

    code = "invalid_data"


class BindingError(base.ValidationError):
    """Plant bindings do not match the plant or the dataset."""

    code = "invalid_binding"


class MissingMeasurementError(GeminiError, ValueError):
    """A bound observation is missing at one tick; the engine skips only that module.

    ``str(error)`` is the skip reason counted in ``Results.skip_counts``.
    """

    code = "missing_value"


class StepError(GeminiError, ValueError):
    """A module failed during a step run with ``on_error="raise"``; the cause is chained."""


class CheckpointError(GeminiError, RuntimeError, ValueError):
    """A checkpoint cannot be saved, loaded or resumed."""


class PlantFormatError(GeminiError, TypeError, ValueError):
    """A saved plant file has another version, plant type or module tree."""

    code = "invalid_format"


class UnknownResultError(GeminiError, KeyError, AttributeError):
    """A results module path or field does not exist."""

    code = "unknown_name"
