"""The assumptions object: sourced defaults only, everything else the user's."""

import pytest
from pydantic import ValidationError as FieldError

import gemini as gm
from gemini.economics import assumptions as module
from gemini.economics.assumptions import Assumptions


def test_only_the_sourced_defaults_are_set():
    """The currency label and the natural-gas factor are the only values nobody gave."""
    given = Assumptions().model_dump()
    assert given["currency"] == "EUR"
    assert given["fuel_emission_factor"] == pytest.approx(56.1 / 1e9)
    assert [name for name, value in given.items() if value is None] == [
        "discount_rate",
        "lifetime_years",
        "electricity_price",
        "fuel_price",
        "heat_price",
        "cold_price",
        "electricity_emission_factor",
    ]


def test_the_object_is_frozen_strict_and_checked():
    """A value cannot change, an unknown name is refused and a negative price is invalid."""
    values = Assumptions(discount_rate=0.05)
    with pytest.raises(FieldError):
        values.discount_rate = 0.1
    with pytest.raises(FieldError):
        Assumptions(discount_rat=0.05)
    with pytest.raises(FieldError):
        Assumptions(heat_price=-1)


def test_resolve_gives_the_defaults_for_none_and_refuses_other_types():
    """``None`` means the defaults; anything but an Assumptions is a validation error."""
    assert module.resolve(None) == Assumptions()
    with pytest.raises(gm.errors.ValidationError, match="Assumptions"):
        module.resolve({"discount_rate": 0.05})


def test_require_names_the_missing_assumption():
    """A value the user must give raises with the code the backend lists."""
    with pytest.raises(gm.errors.ValidationError, match="discount_rate") as error:
        module.require(Assumptions(), "discount_rate")
    assert error.value.code == "missing_value"
    assert error.value.path == "assumptions.discount_rate"
    assert module.require(Assumptions(discount_rate=0.05), "discount_rate") == 0.05


def test_discounting_prefers_the_arguments_and_checks_them():
    """An explicit rate and lifetime win; a lifetime under one year is refused."""
    values = Assumptions(discount_rate=0.05, lifetime_years=20)
    assert module.discounting(values, None, None) == (0.05, 20)
    assert module.discounting(values, 0.0, 10) == (0.0, 10)
    with pytest.raises(gm.errors.ValidationError, match="lifetime"):
        module.discounting(values, None, 0)
    with pytest.raises(gm.errors.ValidationError, match="discount_rate"):
        module.discounting(values, -0.1, None)
