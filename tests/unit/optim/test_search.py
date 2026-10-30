"""Optimisation and sampling keep their final signatures and say they are not built."""

import inspect

import pytest

import gemini as gm


def test_minimize_signature_and_status():
    """The parameters are fixed and the call raises ``NotImplementedYet``."""
    assert list(inspect.signature(gm.optim.minimize).parameters) == [
        "plant",
        "profile",
        "variables",
        "objective",
        "constraints",
        "evaluations",
    ]
    with pytest.raises(gm.errors.NotImplementedYet) as error:
        gm.optim.minimize(None, None, [], "lcoh")
    assert error.value.code == "not_implemented"


def test_sample_signature_and_status():
    """The parameters are fixed and the call raises ``NotImplementedYet``."""
    assert list(inspect.signature(gm.optim.sample).parameters) == [
        "plant",
        "profile",
        "distributions",
        "metrics",
        "count",
        "seed",
    ]
    with pytest.raises(gm.errors.NotImplementedYet):
        gm.optim.sample(None, None, {}, ["lcoh"], 10)
