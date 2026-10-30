"""Inhibitor dosing rates, unchanged stream and limits."""

import pytest

import gemini as gm
from gemini.modules.balance import energy_balance, mass_balance
from gemini.modules.treatment import InhibitorDosing
from gemini.types.flows import Stream
from tests.fixtures.equivalence import assert_module_matches
from tests.fixtures.errors import raises

INLET = Stream(m_dot=50, T=340, p=8e5)


def test_hand_computed_dose_in_ppm():
    """A 20 ppm product dose on 50 kg/s at 40 % active strength."""
    dosing = InhibitorDosing().update_params(product_concentration=0.4)
    result = dosing(inlet=INLET, dose="20 ppm")
    assert result.outputs.product_mass_flow == pytest.approx(1e-3)
    assert result.outputs.active_mass_flow == pytest.approx(4e-4)
    assert result.outlets.outlet == INLET
    assert mass_balance(dosing, result)["residual"] == 0
    assert energy_balance(dosing, result)["relative_residual"] < 1e-12


def test_limits():
    """Zero flow doses nothing; reverse flow, a bad strength and a missing dose raise."""
    dosing = InhibitorDosing().update_params(product_concentration=0.4)
    assert dosing(inlet=INLET.with_(m_dot=0), dose=2e-5).outputs.product_mass_flow == 0
    with pytest.raises(gm.errors.PhysicsError, match="inlet.m_dot"):
        dosing(inlet=INLET.with_(m_dot=-1), dose=2e-5)
    with raises(gm.errors.ValidationError, "missing_value"):
        dosing(inlet=INLET)
    with pytest.raises(gm.errors.ValidationError):
        InhibitorDosing().update_params(product_concentration=0)


def test_inhibitordosing_matches_traced():
    """The dosing rates trace and equal one call per row."""
    module = InhibitorDosing().update_params(product_concentration=0.4)
    rows = [
        dict(inlet=Stream(m_dot=m_dot, T=300, p=1e6), dose=dose)
        for m_dot, dose in [(0, 1e-5), (10, 0), (50, 2e-5)]
    ]
    assert_module_matches(module, rows)
