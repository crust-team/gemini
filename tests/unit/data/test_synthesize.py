"""``gm.data.synthesize``: a stub until the synthesis is built."""

import pytest

import gemini as gm


def test_synthesize_is_not_built_yet():
    """The call is part of the API and says so."""
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.data.synthesize("30 MW", "10 MW", "2027-01-01", "1 d")
