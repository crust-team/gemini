"""One call of one module from plain JSON."""

import pytest

import gemini as gm


def test_evaluate_lands_in_this_step():
    """The name exists with its final parameters."""
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.evaluate("ESP", {}, {}, {})
