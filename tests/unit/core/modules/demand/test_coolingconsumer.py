"""Sensible and latent cooling, dew-point test, return limits and balances."""

import pytest

from gemini.core.modules import CoolingConsumer, energy_balance, mass_balance
from gemini.core.physics import psychrometrics
from gemini.core.types import Stream
from gemini.errors import DeclarationError, MissingValueError, PhysicsRangeError

CP = 4217.4
SUPPLY = Stream(m_dot=2.0, T=280.15, p=3e5)
INDOOR = dict(indoor_temperature="24 C", indoor_relative_humidity=0.5)
AVAILABLE = 2 * CP * 9


def _consumer():
    return CoolingConsumer().update_params(maximum_return_temperature="16 C", dew_point_margin=3)


def _call(consumer, supply=SUPPLY, sensible=5e4, latent=1e4, **indoor):
    return consumer(
        supply_in=supply,
        sensible_cooling_demand=sensible,
        latent_cooling_demand=latent,
        **(INDOOR | indoor),
    )


def test_met_loads_warm_the_return_and_close_the_balance():
    """Both loads are met below the dew point and warm the water by Q / (m_dot cp)."""
    consumer = _consumer()
    result = _call(consumer)
    out, return_out = result.outputs, result.outlets.return_out
    assert out.heat_absorbed == 6e4 and out.unmet_sensible == 0 and out.unmet_latent == 0
    assert not out.is_unmet
    assert out.return_out_T == pytest.approx(280.15 + 6e4 / (2 * CP)) == return_out.T
    assert out.dew_point == pytest.approx(psychrometrics.dew_point(297.15, 0.5))
    assert out.dew_point - 273.15 == pytest.approx(12.95, abs=0.01)
    assert return_out.m_dot == SUPPLY.m_dot and return_out.p == SUPPLY.p
    balance = energy_balance(consumer, result)
    assert balance["relative_residual"] < 1e-12 and balance["heat_absorbed"] == 6e4
    assert mass_balance(consumer, result)["residual"] == 0


def test_short_capacity_serves_the_sensible_load_first():
    """At the return limit the sensible load is met first and the latent load takes the rest."""
    consumer = _consumer()
    out = _call(consumer, sensible=7e4, latent=2e4).outputs
    assert out.unmet_sensible == 0
    assert out.unmet_latent == pytest.approx(9e4 - AVAILABLE) and out.is_unmet
    assert out.heat_absorbed == pytest.approx(AVAILABLE) and out.return_out_T == 289.15
    result = _call(consumer, sensible=1e5, latent=2e4)
    assert result.outputs.unmet_sensible == pytest.approx(1e5 - AVAILABLE)
    assert result.outputs.unmet_latent == 2e4
    assert energy_balance(consumer, result)["relative_residual"] < 1e-12


def test_supply_above_the_dew_point_margin_leaves_the_latent_load_unmet():
    """A supply warmer than T_dew - margin does not dehumidify; the sensible load is still met."""
    consumer = _consumer()
    threshold = psychrometrics.dew_point(297.15, 0.5) - 3
    out = _call(consumer, supply=SUPPLY.with_(T=threshold + 0.01), sensible=3e4).outputs
    assert out.unmet_latent == 1e4 and out.unmet_sensible == 0 and out.heat_absorbed == 3e4
    assert out.is_unmet
    out = _call(consumer, supply=SUPPLY.with_(T=threshold - 0.01), sensible=3e4).outputs
    assert out.unmet_latent == 0 and out.heat_absorbed == 4e4 and not out.is_unmet


def test_indoor_temperature_limits_the_return():
    """The water cannot return warmer than the indoor air; a warm supply absorbs nothing."""
    consumer = _consumer()
    out = _call(consumer, sensible=1e6, indoor_temperature="12 C").outputs
    assert out.return_out_T == 285.15 and out.heat_absorbed == pytest.approx(2 * CP * 5)
    out = _call(consumer, supply=SUPPLY.with_(T=300.0)).outputs
    assert out.heat_absorbed == 0 and out.return_out_T == 300.0 and out.unmet_sensible == 5e4


def test_zero_flow_and_zero_demand():
    """No flow absorbs nothing; no demand leaves the stream unchanged and nothing unmet."""
    consumer = _consumer()
    result = _call(consumer, supply=SUPPLY.with_(m_dot=0))
    assert result.outputs.heat_absorbed == 0 and result.outlets.return_out.T == SUPPLY.T
    assert result.outputs.unmet_sensible == 5e4 and result.outputs.unmet_latent == 1e4
    assert energy_balance(consumer, result)["relative_residual"] < 1e-12
    out = _call(consumer, sensible=0, latent=0).outputs
    assert out.heat_absorbed == 0 and not out.is_unmet and out.return_out_T == SUPPLY.T


def test_invalid_inputs_raise():
    """Reverse flow, dry air, negative loads and missing values are rejected."""
    consumer = _consumer()
    with pytest.raises(PhysicsRangeError, match="supply_in.m_dot = -1"):
        _call(consumer, supply=SUPPLY.with_(m_dot=-1))
    with pytest.raises(DeclarationError):
        _call(consumer, indoor_relative_humidity=0)
    with pytest.raises(DeclarationError):
        _call(consumer, latent=-1)
    with pytest.raises(DeclarationError):
        consumer.update_params(dew_point_margin=-1)
    with pytest.raises(MissingValueError):
        consumer(supply_in=SUPPLY, sensible_cooling_demand=1e4, latent_cooling_demand=0)
