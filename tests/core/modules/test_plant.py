"""Graph stream routing, buried ESP placement and feedback convergence."""

import math
from pathlib import Path

import pytest
from pydantic import Field

from gemini.core.base.stream import Stream
from gemini.core.config.build import build_plant
from gemini.core.config.gemini_loader import load_gemini
from gemini.core.modules.module import EmptyModel, Module, ModuleResult
from gemini.core.modules.plant import GraphPlant


class Relaxation(Module):
    """Feedback fixture approaching a fixed temperature without changing mass."""

    name = "relaxation"
    category = "test"
    inlets = ("inlet",)
    outlets = ("outlet",)

    class Params(EmptyModel):
        """Temperature relaxation factor and target."""

        factor: float = Field(0.5, description="Retained temperature deviation [-]")
        target: float = Field(320, description="Fixed-point temperature [K]")

    def forward(self, inputs, streams_in):
        """Relax toward the fixed point; factor one instead adds one kelvin."""
        stream = streams_in["inlet"]
        T = self.params.target + self.params.factor * (stream.T - self.params.target)
        if self.params.factor == 1:
            T = stream.T + 1
        return ModuleResult(self.Outputs(), {"outlet": stream.with_(T=T)})


def test_tear_convergence_and_failure():
    """Feedback iteration converges by stream tolerances or reports the remaining residuals."""
    link = dict(source="a", source_port="outlet", target="a", target_port="inlet")
    plant = GraphPlant({"a": Relaxation()}, [link])
    plant()
    assert plant.last_results["a"].streams["outlet"].T == pytest.approx(320, abs=1e-3)
    plant.a.update_params(factor=1)
    with pytest.raises(RuntimeError, match="50 iterations; residuals"):
        plant()
    with pytest.raises(ValueError, match="unknown target port"):
        GraphPlant({"a": Relaxation()}, [link | {"target_port": "wrong"}])
    with pytest.raises(ValueError, match="multiple sources"):
        GraphPlant({"a": Relaxation()}, [link, link])


def test_example_graph_and_split_helpers():
    """Every connection carries a finite stream and the buried-pump split matches well helpers."""
    data = Path(__file__).parents[3] / "datasets/geothermal_doublet"
    config = load_gemini(data)
    plant = build_plant(config)
    inputs = {"reservoir_c1b5": {"m_dot": 149.191 / 3600 * 1068}, "esp_1ee3": {"frequency": 60}}
    secondary = Stream(
        m_dot=160 / 3600 * 1068, T=293.15, p=5e5, fluid=config.modules["esp_1ee3"].fluid
    )
    result = plant(inputs, {"heat_exchanger_3410.cold_in": secondary})
    assert len(plant.last_link_streams) == len(config.links)
    for stream in plant.last_link_streams.values():
        assert all(math.isfinite(getattr(stream, field)) for field in ("p", "T", "m_dot"))
    well = plant.production_well_c774
    bottom = plant.last_results["reservoir_c1b5"].streams["sandface"]
    assert (
        well.intake_conditions(bottom)
        == plant.last_results["production_well_c774"].streams["wellhead"]
    )
    discharge = plant.last_results["esp_1ee3"].streams["discharge"]
    assert (
        well.wellhead_from_discharge(discharge)
        == plant.last_results["production_well_c774_riser"].streams["wellhead"]
    )
    assert set(result.streams) == set(plant.outlets)
    assert set(result.outputs.root) == config.modules.keys()
