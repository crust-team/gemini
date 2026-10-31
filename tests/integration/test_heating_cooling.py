"""The heating and cooling template and its presets run one simulate with stated assumptions."""

import pytest

import gemini as gm
from tests.fixtures.heating_cooling import configure, filled_spec, two_ticks

pytestmark = pytest.mark.slow

PRESETS = {
    "heating_only": {},
    "heating_absorption_cooling": {},
    "heating_heat_pump_compression_cooling": {},
    "heating_full_cooling": {},
}
FLAGS = {
    "everything": {},
    "no_peak_boiler": {"peak_boiler.enabled": False},
    "no_sorption": {"absorption_chiller.enabled": False, "adsorption_chiller.enabled": False},
    "no_cooling": {"cooling_loop.enabled": False},
}


def _run(spec):
    plant = configure(gm.plants.from_spec(spec))
    results = gm.simulate(plant, two_ticks(), on_error="raise")
    return plant, results


@pytest.mark.parametrize("name", PRESETS)
def test_every_preset_runs_one_simulate(name):
    """A preset builds, validates and runs two ticks without a row error."""
    spec = filled_spec(name)
    assert gm.plants.validate(spec) == []
    plant, results = _run(spec)
    assert results.errors() == []
    frame = results.to_frame()
    delivered = frame["heating_consumer.supply_in.enthalpy_flow"]
    delivered = delivered - frame["heating_consumer.return_out.enthalpy_flow"]
    assert delivered.tolist() == pytest.approx([1e5, 1e5])


@pytest.mark.parametrize("flags", FLAGS.values(), ids=FLAGS)
def test_the_full_template_runs_with_units_switched_off(flags):
    """Units leave with their wiring and the rest still runs; chillers drive off the hot water."""
    spec = filled_spec("heating_cooling", flags)
    plant, results = _run(spec)
    assert results.errors() == []
    assert ("cooling_consumer" in results.names()) == ("cooling_loop.enabled" not in flags)
    assert ("peak_boiler" in results.names()) == ("peak_boiler.enabled" not in flags)
    assert results.get("heating_consumer", "unmet_demand")["values"] == [0.0, 0.0]
    if not flags:
        assert min(results.get("absorption_chiller", "evaporator_duty")["values"]) > 0
        assert results.get("cooling_consumer", "unmet_sensible")["values"] == [0.0, 0.0]
