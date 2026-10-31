"""An evaluation holds the arrays of a result tree; literals broadcast and declared types apply."""

import numpy as np

from gemini.engine.evaluation import Evaluation, converter


def test_the_converter_maps_literals_lists_and_none_to_arrays_of_rows():
    """A number broadcasts, a list stacks to ``(rows, n)``, ``None`` is NaN, an array stays."""
    convert = converter(3)
    assert convert(2.0).tolist() == [2.0] * 3
    assert convert(True).dtype == bool
    assert convert([1.0, 2.0]).shape == (3, 2)
    assert np.isnan(convert(None)).all()
    assert convert(np.array(4.0)).tolist() == [4.0] * 3
    assert convert(np.array([1.0, 2.0, 3.0])).tolist() == [1.0, 2.0, 3.0]
    assert convert([]).shape == (3, 0)


def test_traced_values_are_mapped_by_the_column_function():
    """A value of a traced type goes to ``column``, also inside a list."""
    convert = converter(2, (str,), lambda value: np.full(2, len(value)))
    assert convert("abc").tolist() == [3, 3]
    assert convert(["a", "bb"]).tolist() == [[1, 2], [1, 2]]


def test_an_evaluation_raises_the_exception_of_its_first_failed_row():
    """A failed row has its own exception; no failed row raises nothing."""
    errors = {1: ValueError("second"), 2: KeyError("third")}
    evaluation = Evaluation(3, np.array([False, True, True]), None, errors.__getitem__)
    try:
        evaluation.raise_first()
    except ValueError as error:
        assert str(error) == "second"
    Evaluation(3, np.zeros(3, dtype=bool), None, errors.__getitem__).raise_first()
    assert evaluation.breaks == [] and evaluation.stepped is False
