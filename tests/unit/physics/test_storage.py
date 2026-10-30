"""Mixed tank balance, coil conductance and the phase segments of an ice store."""

import math

import pytest

from gemini.physics import storage
from tests.fixtures.equivalence import assert_function_matches

ICE = dict(
    water_mass=1000.0,
    latent_heat=storage.DEFAULT_LATENT_HEAT,
    freezing_temperature=273.15,
    water_heat_capacity=storage.DEFAULT_WATER_HEAT_CAPACITY,
    ice_heat_capacity=storage.DEFAULT_ICE_HEAT_CAPACITY,
)


def ice(fraction, temperature, duration, inlet, conductance):
    return storage.ice_advance(fraction, temperature, duration, inlet, conductance, **ICE)


def test_tank_relations_by_hand():
    """Equilibrium of two circuits and a loss; the hot tank and the chilled tank flip signs."""
    assert storage.circuit_conductance(0.8, 500.0) == 400.0
    assert storage.tank_capacity(4.2e6, 2.0) == 8.4e6
    stored, charge, discharge = storage.tank_service_report(True, 1e6, 330.0, 300.0, 20.0, 5.0)
    assert (stored, charge, discharge) == (3e7, 20.0, -5.0)
    stored, charge, discharge = storage.tank_service_report(False, 1e6, 280.0, 300.0, 20.0, 5.0)
    assert (stored, charge, discharge) == (2e7, -20.0, 5.0)
    far = storage.tank_relaxation(300.0, 1e6, 1e12, 100.0, 340.0, 50.0, 320.0, 10.0, 290.0)
    assert far == pytest.approx((100 * 340 + 50 * 320 + 10 * 290) / 160, rel=1e-9)
    once = storage.tank_relaxation(300.0, 1e6, 1e4, 100.0, 340.0, 0.0, 0.0, 0.0, 0.0)
    assert once == pytest.approx(340 + (300 - 340) * math.exp(-1e6 * 0 - 100 * 1e4 / 1e6))
    assert storage.tank_relaxation(300.0, 1e6, 10.0, 0.0, 340.0, 0.0, 0.0, 0.0, 0.0) == 300.0


def test_ice_latent_segment_freezes_linearly_by_hand():
    """A glycol inlet 5 K below freezing at G = 2000 W/K freezes M L x worth of water at 10 kW."""
    cold = ICE["water_mass"] * ICE["latent_heat"]
    assert storage.ice_stored_cold(1000.0, storage.DEFAULT_LATENT_HEAT, 0.5) == 0.5 * cold
    fraction, temperature = ice(0.0, 273.15, 3600.0, 268.15, 2000.0)
    assert temperature == 273.15
    assert fraction == pytest.approx(1e4 * 3600 / cold)
    fraction, temperature = ice(0.5, 273.15, 3600.0, 278.15, 2000.0)
    assert fraction == pytest.approx(0.5 - 1e4 * 3600 / cold)


def test_ice_sensible_segment_relaxes_and_stops_at_freezing():
    """Water above freezing relaxes with M c / G; a long step ends frozen at its temperature."""
    constant = 1000.0 * storage.DEFAULT_WATER_HEAT_CAPACITY / 2000.0
    fraction, temperature = ice(0.0, 283.15, 100.0, 293.15, 2000.0)
    assert fraction == 0
    assert temperature == pytest.approx(293.15 - 10 * math.exp(-100 / constant))
    fraction, temperature = ice(0.0, 275.15, 1e4, 268.15, 2000.0)
    assert 0 < fraction < 1 and temperature == 273.15
    fraction, temperature = ice(0.0, 275.15, 1e9, 268.15, 2000.0)
    assert fraction == 1 and temperature < 273.15
    assert ice(0.3, 273.15, 100.0, 268.15, 0.0) == (0.3, 273.15)


ROWS = [
    (0.0, 273.15, 3600.0, 268.15, 2000.0),
    (0.5, 273.15, 3600.0, 278.15, 2000.0),
    (0.5, 273.15, 3600.0, 273.15, 2000.0),
    (0.0, 283.15, 100.0, 293.15, 2000.0),
    (0.0, 275.15, 1e6, 268.15, 2000.0),
    (1.0, 268.15, 1e6, 280.15, 2000.0),
    (0.0, 275.15, 1e9, 268.15, 2000.0),
    (0.3, 273.15, 100.0, 268.15, 0.0),
]


def test_ice_functions_match_on_arrays_over_every_branch():
    """Liquid, solid, latent, stopped and multi-segment steps agree on arrays."""
    assert_function_matches(storage.ice_advance, ROWS, **ICE)
    assert_function_matches(storage.ice_step, ROWS, **ICE)
    assert_function_matches(storage.ice_stored_cold, [(1000.0, 333550.0, 0.5), (1.0, 2.0, 0.0)])


def test_tank_functions_match_on_arrays():
    """Both services, stopped tanks and long steps agree on arrays."""
    assert_function_matches(storage.circuit_conductance, [(0.8, 500.0), (1.0, 0.0)])
    assert_function_matches(storage.tank_capacity, [(4.2e6, 2.0)])
    assert_function_matches(
        storage.tank_service_report,
        [(True, 1e6, 330.0, 300.0, 20.0, 5.0), (False, 1e6, 280.0, 300.0, 20.0, 5.0)],
    )
    assert_function_matches(
        storage.tank_relaxation,
        [
            (300.0, 1e6, 1e4, 100.0, 340.0, 50.0, 320.0, 10.0, 290.0),
            (300.0, 1e6, 1e4, 0.0, 340.0, 0.0, 320.0, 0.0, 290.0),
        ],
    )
