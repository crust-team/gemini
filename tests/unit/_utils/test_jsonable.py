"""Plain JSON from NumPy, pandas and time values."""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from pydantic import BaseModel

from gemini._utils.jsonable import to_plain


def test_numpy_values_become_python():
    """Scalars and arrays leave NumPy."""
    result = to_plain({"a": np.float64(1.5), "b": np.int64(2), "c": np.bool_(True)})
    assert result == {"a": 1.5, "b": 2, "c": True}
    assert type(result["a"]) is float and type(result["b"]) is int and type(result["c"]) is bool
    assert to_plain(np.array([[1.0, 2.0]])) == [[1.0, 2.0]]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), np.nan, -np.inf])
def test_non_finite_numbers_become_none(value):
    """JSON has no NaN or infinity."""
    assert to_plain([value]) == [None]


def test_containers_times_and_keys():
    """Tuples, series and times are readable by ``json.dumps(allow_nan=False)``."""
    time = datetime(2024, 7, 1, tzinfo=timezone.utc)
    value = {1: (1.0, None), "t": time, "s": pd.Series([1.0, np.nan])}
    result = to_plain(value)
    assert result == {"1": [1.0, None], "t": "2024-07-01T00:00:00+00:00", "s": [1.0, None]}
    assert json.dumps(result, allow_nan=False)


def test_a_pydantic_model_becomes_its_fields():
    """A declared value such as a pipe path is data."""

    class Section(BaseModel):
        """One field."""

        length: float

    assert to_plain([Section(length=2.0)]) == [{"length": 2.0}]


def test_an_unknown_value_is_refused():
    """A value with no JSON form raises instead of being dropped."""
    with pytest.raises(TypeError, match="expected a JSON-like value"):
        to_plain(object())
