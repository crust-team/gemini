"""Module descriptions, schemas and parameter checks."""

import pytest

import gemini as gm


def test_description_lands_in_this_step():
    """The name exists on classes and instances."""
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.modules.ESP.describe()
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.modules.ESP().parameter_schema()
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.modules.ESP.validate_params({})
