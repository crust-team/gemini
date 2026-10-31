"""Calibration argument checks and result reporting; replay fits are integration tests."""

import pytest

import gemini as gm
from gemini.analysis.calibrate import CalibrationResult
from gemini.errors import ValidationError
from tests.fixtures.errors import raises


def test_parameters_must_be_one_calibratable_set_of_the_plant(fresh_plant, reference_dataset):
    """Empty, uncalibratable, mixed, duplicate and foreign parameters are rejected."""
    plant, data = fresh_plant, reference_dataset
    ua = plant.get("heat_exchanger.thermal_conductance")
    head = plant.get("doublet.esp.head_coefficients")
    with pytest.raises(ValueError, match="at least one"):
        gm.analysis.calibrate(plant, data, [])
    with raises(
        ValidationError, "invalid_design", match="heat_exchanger.arrangement.*calibratable"
    ):
        gm.analysis.calibrate(plant, data, [plant.get("heat_exchanger.arrangement")])
    with raises(ValidationError, "invalid_design", match="doublet.esp, heat_exchanger"):
        gm.analysis.calibrate(plant, data, [ua, head])
    with raises(
        ValidationError, "invalid_design", match="heat_exchanger.thermal_conductance.*twice"
    ):
        gm.analysis.calibrate(plant, data, [ua, ua])
    foreign = gm.modules.exchangers.HeatExchanger()
    with raises(ValidationError, "invalid_design", match="supplied plant"):
        gm.analysis.calibrate(plant, data, [foreign.get("thermal_conductance")])


def test_modules_without_measured_bindings_cannot_be_fitted(fresh_plant, reference_dataset):
    """A module with no measured output binding names what is missing."""
    plant = fresh_plant
    plant.bindings["heat_exchanger"].measured.clear()
    with raises(ValidationError, "invalid_binding", match="heat_exchanger: measured"):
        gm.analysis.calibrate(
            plant, reference_dataset, [plant.get("heat_exchanger.thermal_conductance")]
        )


def test_result_repr_shows_change_and_residuals():
    """The representation names every fitted value and the RMS improvement."""
    result = CalibrationResult(
        fitted={"thermal_conductance": 2.0},
        rms_before=1.0,
        rms_after=0.5,
        observations=3,
        success=True,
        message="ok",
        applied=False,
        initial={"thermal_conductance": 1.0},
        rms_by_output_before={"duty": 1.0},
        rms_by_output_after={"duty": 0.5},
        evaluations=4,
    )
    assert repr(result) == (
        "CalibrationResult(thermal_conductance: 1.0 -> 2.0; RMS 1 -> 0.5; evaluations=4, "
        "success=True, applied=False)"
    )
