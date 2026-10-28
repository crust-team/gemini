"""Heat exchanger energy balances and validation against the example plant dataset."""

from pathlib import Path

import pandas as pd
import pytest

from gemini.core.modules.heat import HeatExchanger
from gemini.core.physics import units
from gemini.core.types.flows import Stream
from gemini.core.types.fluid import WATER
from gemini.legacy import tables as mapping


def test_measured_heat_exchanger_performance():
    """Fit UA from measured terminal temperatures, then reproduce duty, temperatures and loss."""
    data = Path(__file__).parents[5] / "examples/legacy/gemini_project_bridge/old_project"
    rows = pd.read_csv(data / "doublet_2024_old.csv", sep=";", nrows=5)
    base = mapping.heatexchanger_params_from_gemini(
        mapping.read_property(data / "heat_exchanger_3410.param")
    )
    for _, r in rows.iterrows():
        # NOTE(refactor): CSV implies rho*cp=4.410 MJ/m3/K, unlike default water's 4.2174.
        # Density 1050 kg/m3 with the retained cp=4217.4 predicts duty within 0.5%.
        mh, mc = units.m3h_to_m3s(r.Qp) * 1050, units.m3h_to_m3s(r.Qs) * 1050
        measured = dict(
            hot_in_T=units.c_to_k(r.T_p_in),
            hot_out_T=units.c_to_k(r.T_p_out),
            cold_in_T=units.c_to_k(r.T_s_in),
            cold_out_T=units.c_to_k(r.T_s_out),
            m_dot_hot=mh,
            m_dot_cold=mc,
        )
        ua = HeatExchanger.ua_from_measurements(**measured)
        params = base | dict(
            ua=ua,
            dp_hot_nominal=units.bar_to_pa(r.HEX_PDrop),
            dp_cold_nominal=0,
            m_dot_hot_nominal=mh,
            m_dot_cold_nominal=mc,
        )
        c = HeatExchanger(**params)
        streams = {
            "hot_in": Stream(m_dot=mh, T=measured["hot_in_T"], p=units.bar_to_pa(r.HEX_Pin)),
            "cold_in": Stream(m_dot=mc, T=measured["cold_in_T"], p=1e6, fluid=WATER),
        }
        out = c(**streams).outputs
        assert out.hot_out_T == pytest.approx(measured["hot_out_T"], abs=0.5)
        assert out.cold_out_T == pytest.approx(measured["cold_out_T"], abs=0.5)
        assert out.duty == pytest.approx(r.Thermal_PowerGen, rel=0.02)
        assert 10000 < out.dp_hot < 20000
        assert not c.health(out, measured).alarm
        fouled = HeatExchanger(**(params | {"ua": ua * 0.8}))
        reduced = fouled(**streams).outputs
        degraded = measured | dict(hot_out_T=reduced.hot_out_T, cold_out_T=reduced.cold_out_T)
        assert c.health(out, degraded).alarm


@pytest.mark.parametrize("arrangement", ["parallel", "counterflow"])
def test_first_law_equal_capacity_and_limits(arrangement):
    """Both arrangements conserve energy, retain mass and respect zero-flow/zero-UA limits."""
    p = dict(
        ua=100000,
        arrangement=arrangement,
        dp_hot_nominal=1000,
        dp_cold_nominal=2000,
        m_dot_hot_nominal=10,
        m_dot_cold_nominal=10,
    )
    c = HeatExchanger(**p)
    hot, cold = Stream(m_dot=10, T=350, p=1e6), Stream(m_dot=10, T=300, p=1e6)
    result = c(hot_in=hot, cold_in=cold)
    out, streams = result.outputs, result.outlets
    assert (hot.T - out.hot_out_T) * 10 * 4217.4 == pytest.approx(out.duty)
    assert (out.cold_out_T - cold.T) * 10 * 4217.4 == pytest.approx(out.duty)
    assert streams["hot_out"].m_dot == hot.m_dot and streams["cold_out"].m_dot == cold.m_dot
    assert streams["hot_out"].p == hot.p - 1000
    out = c(hot_in=hot.with_(m_dot=0), cold_in=cold).outputs
    assert out.duty == 0
    c.update_params(ua=0)
    out = c(hot_in=hot, cold_in=cold).outputs
    assert out.duty == 0 and out.hot_out_T == hot.T
    out = c(hot_in=hot, cold_in=cold.with_(T=350)).outputs
    assert out.duty == 0 and out.lmtd == 0


def test_invalid_measurements():
    """A temperature cross or a gross heat-balance mismatch cannot identify a valid UA."""
    with pytest.raises(ValueError):
        HeatExchanger.ua_from_measurements(350, 340, 300, 340, 10, 10)
