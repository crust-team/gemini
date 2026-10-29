"""Errors in datasets, clocks, bindings, runs, results, plant files and checkpoints."""

from gemini.errors.base import GeminiError


class DatasetError(GeminiError, TypeError, ValueError):
    """A dataset cannot be built from, or read with, the given data."""


class ClockError(GeminiError, KeyError, ValueError):
    """A clock is invalid, or a timestamp is not one of its ticks."""


class BindingError(GeminiError, ValueError):
    """Plant bindings do not match the plant or the dataset."""


class MissingMeasurementError(GeminiError, ValueError):
    """A bound observation is missing at one tick; the engine skips only that module.

    ``str(error)`` is the skip reason counted in ``Results.skip_counts``.
    """


class StepError(GeminiError, ValueError):
    """A module failed during a step run with ``on_error="raise"``; the cause is chained."""


class CheckpointError(GeminiError, RuntimeError, ValueError):
    """A checkpoint cannot be saved, loaded or resumed."""


class PlantFormatError(GeminiError, TypeError, ValueError):
    """A saved plant file has another version, plant type or module tree."""


class UnknownResultError(GeminiError, KeyError, AttributeError):
    """A results module path or field does not exist."""
