"""Calibration argument checks and result reporting; replay fits are integration tests."""

import pytest

import gemini as gm
from gemini.errors import BindingError, ConfigurationError
from gemini.optim import CalibrationResult


def test_parameters_must_be_one_calibratable_set_of_the_plant(fresh_plant, reference_dataset):
    """Empty, uncalibratable, mixed, duplicate and foreign parameters are rejected."""
    plant, data = fresh_plant, reference_dataset
    ua = plant.get_parameter("heat_exchanger.ua")
    head = plant.get_parameter("doublet.esp.head_coeff")
    with pytest.raises(ValueError, match="at least one"):
        gm.optim.calibrate(plant, data, [])
    with pytest.raises(ConfigurationError, match="heat_exchanger.arrangement.*calibratable"):
        gm.optim.calibrate(plant, data, [plant.get_parameter("heat_exchanger.arrangement")])
    with pytest.raises(ConfigurationError, match="doublet.esp, heat_exchanger"):
        gm.optim.calibrate(plant, data, [ua, head])
    with pytest.raises(ConfigurationError, match="heat_exchanger.ua.*twice"):
        gm.optim.calibrate(plant, data, [ua, ua])
    foreign = gm.modules.exchangers.HeatExchanger()
    with pytest.raises(ConfigurationError, match="supplied plant"):
        gm.optim.calibrate(plant, data, [foreign.get_parameter("ua")])


def test_modules_without_measured_bindings_cannot_be_fitted(fresh_plant, reference_dataset):
    """A module with no measured output binding names what is missing."""
    plant = fresh_plant
    plant.bindings["heat_exchanger"].measured.clear()
    with pytest.raises(BindingError, match="heat_exchanger: measured"):
        gm.optim.calibrate(plant, reference_dataset, [plant.get_parameter("heat_exchanger.ua")])


def test_result_repr_shows_change_and_residuals():
    """The representation names every fitted value and the RMS improvement."""
    result = CalibrationResult(
        fitted={"ua": 2.0},
        rms_before=1.0,
        rms_after=0.5,
        observations=3,
        success=True,
        message="ok",
        applied=False,
        initial={"ua": 1.0},
        rms_by_output_before={"duty": 1.0},
        rms_by_output_after={"duty": 0.5},
        evaluations=4,
    )
    assert repr(result) == (
        "CalibrationResult(ua: 1.0 -> 2.0; RMS 1 -> 0.5; evaluations=4, success=True, "
        "applied=False)"
    )
