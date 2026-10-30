"""Plants built from data."""

import json

import pytest

import gemini as gm
from gemini.core.modules.plants import library
from gemini.errors import NotImplementedYet, UnknownNameError, ValidationError


@pytest.fixture
def chain():
    """Return a degasser, a filter and a second filter, wired by automatic matching."""
    plant = gm.Plant("Chain")
    plant.add("Degasser", "degasser")
    plant.add("Filter", "first")
    plant.add("Filter", "second")
    plant.connect("degasser", "first")
    plant.connect("first.outlet", "second.inlet")
    return plant


def stream():
    """Return a brine stream."""
    return gm.Stream(m_dot=10.0, T=350.0, p=5e5)


def test_a_plant_is_a_module_in_the_plant_category():
    """A built plant is a normal composite."""
    assert isinstance(gm.Plant("doublet"), gm.modules.Module)
    assert gm.Plant.category == "plant"
    assert gm.Plant().name == "plant"


def test_names_follow_the_type_and_free_ports_become_plant_ports(chain):
    """An unconnected child port is a plant port named from its path."""
    assert list(chain.inlets()) == ["degasser_inlet"]
    assert list(chain.outlets()) == ["degasser_gas", "second_outlet"]
    assert chain.add("Filter").name == "filter"
    assert "filter_2" not in dict(chain.named_children())
    assert chain.add("Filter") is chain.get_module("filter_2")


def test_a_built_plant_runs_in_connection_order(chain):
    """The degasser feeds the filters; the plant outlets are the free outlets."""
    result = chain(degasser_inlet=stream())
    assert [name for name, _ in result.call_records] == ["degasser", "first", "second"]
    assert result.outlets.degasser_gas.m_dot < 10.0


def test_a_bare_word_names_a_plant_port(chain):
    """``connect("name", "path.port")`` names a plant inlet and is stored beside the wiring."""
    plant = gm.Plant("Named")
    plant.add("Filter", "filter")
    plant.connect("feed", "filter.inlet")
    plant.connect("filter.outlet", "product")
    spec = plant.to_spec()
    assert spec["inlets"] == {"feed": "filter.inlet"}
    assert spec["outlets"] == {"product": "filter.outlet"}
    assert spec["connections"] == []
    assert list(plant.inlets()) == ["feed"] and list(plant.outlets()) == ["product"]


def test_connection_list_gives_streams_and_kind(chain):
    """The typed end names the stream; both ends untyped give null."""
    assert chain.connection_list() == [
        {"source": "degasser.liquid", "target": "first.inlet", "stream": "brine", "kind": None},
        {"source": "first.outlet", "target": "second.inlet", "stream": "brine", "kind": None},
    ]
    plant = gm.Plant("Untyped")
    plant.add("Pipe", "one")
    plant.add("Pipe", "two")
    plant.connect("one.outlet", "two.inlet", kind="state")
    assert plant.connection_list() == [
        {"source": "one.outlet", "target": "two.inlet", "stream": None, "kind": "state"}
    ]


def test_summary_is_a_table_with_totals(chain):
    """One row per module with type, category, inbound connections and parameter count."""
    lines = chain.summary().splitlines()
    assert lines[0] == "Plant: Chain"
    assert lines[1].split() == ["Module", "Type", "Category", "Connected", "to", "Parameters"]
    assert "inlet <- degasser.liquid" in lines[3]
    assert lines[-1].startswith("Total parameters: ")


def test_an_inlet_has_one_source_and_an_outlet_one_target(chain):
    """A second connection to a used port raises ``port_in_use``."""
    chain.add("Filter", "third")
    with pytest.raises(ValidationError) as caught:
        chain.connect("first.outlet", "third.inlet")
    assert caught.value.code == "port_in_use" and caught.value.path == "source"
    with pytest.raises(ValidationError) as caught:
        chain.connect("degasser.liquid", "second.inlet")
    assert caught.value.code == "port_in_use"


def test_ambiguous_matches_list_the_candidates():
    """Two fitting pairs raise ``ambiguous_port`` naming both."""
    plant = gm.Plant("Split")
    plant.add("Splitter", "splitter")
    plant.add("HeatExchanger", "exchanger")
    with pytest.raises(ValidationError) as caught:
        plant.connect("splitter", "exchanger")
    assert caught.value.code == "ambiguous_port"
    assert len(caught.value.suggestions) == 4
    assert "splitter.first_out [any] -> exchanger.hot_in [any]" in caught.value.suggestions


def test_a_stream_type_mismatch_is_refused(chain):
    """A gas outlet cannot feed a brine inlet."""
    chain.add("Filter", "third")
    with pytest.raises(ValidationError) as caught:
        chain.connect("degasser.gas", "third.inlet")
    assert caught.value.code == "stream_mismatch"


def test_a_loop_needs_a_state_connection(chain):
    """A cycle raises ``loop_without_state``; the same wire as state is accepted."""
    with pytest.raises(ValidationError) as caught:
        chain.connect("second.outlet", "degasser.inlet")
    assert caught.value.code == "loop_without_state"
    assert len(chain.connection_list()) == 2
    chain.connect("second.outlet", "degasser.inlet", kind="state")
    with pytest.raises(NotImplementedYet):
        chain(**{name: stream() for name in chain.inlets()})


def test_unknown_names_come_with_suggestions(chain):
    """Modules and ports that do not exist suggest the closest ones."""
    with pytest.raises(UnknownNameError) as caught:
        chain.connect("frist.outlet", "second.inlet")
    assert caught.value.suggestions == ("first",)
    chain.add("Filter", "third")
    with pytest.raises(ValidationError) as caught:
        chain.connect("second.outlt", "third.inlet")
    assert caught.value.code == "unknown_port" and caught.value.suggestions == ("outlet",)


def test_connections_reach_through_groups_but_never_into_plants():
    """``filters.hot.outlet`` is valid; ``doublet.esp.discharge`` is not."""
    plant = gm.Plant("Reach")
    plant.add("ModuleDict", "filters")
    plant.add("Filter", "filters.hot")
    plant.add("Filter", "filters.cold")
    plant.add("Doublet", "doublet")
    plant.connect("filters.hot.outlet", "filters.cold.inlet")
    with pytest.raises(ValidationError) as caught:
        plant.connect("doublet.esp.discharge", "filters.hot.inlet")
    assert caught.value.code == "invalid_connection"
    assert "supply_out" in str(caught.value)
    with pytest.raises(ValidationError):
        plant.connect("filters", "doublet")


def test_a_plant_child_in_a_false_cycle_is_opened():
    """The doublet loop through the surface equipment runs the doublet's children directly."""
    plant = library.build("DoubletHeatPlant")
    paths = [step.path for step in plant._compiled().steps]
    assert paths == [
        "doublet.reservoir",
        "doublet.well",
        "doublet.esp",
        "doublet.riser",
        "degasser",
        "filters.hot",
        "heat_exchanger",
        "filters.cold",
        "injection_pump",
        "doublet.injector",
        "doublet.sink",
    ]


def test_a_plant_child_outside_a_cycle_is_called_as_one_unit():
    """Alone, the nested doublet is a single step and a record named after it."""
    plant = gm.Plant("Nested")
    plant.add("Doublet", "doublet")
    assert [step.path for step in plant._compiled().steps] == ["doublet"]
    assert list(plant.inlets()) == ["doublet_return_in"]


def test_the_doublet_runs_injection_before_production():
    """Ties go to the first appearance in the connection list, as the handwritten forward."""
    plant = library.build("Doublet")
    paths = [step.path for step in plant._compiled().steps]
    assert paths == ["injector", "sink", "reservoir", "well", "esp", "riser"]


def test_to_spec_is_json_and_validate_is_empty(chain):
    """The spec is plain JSON, rebuilds an equal plant and has no problems."""
    spec = chain.to_spec()
    assert json.loads(json.dumps(spec, allow_nan=False)) == spec
    assert chain.validate() == []
    assert gm.plants.from_spec(spec).to_spec() == spec


def test_simulate_calls_the_engine_with_the_plant(monkeypatch):
    """``Plant.simulate(profile)`` is ``Engine(plant).simulate(profile)``."""
    calls = []

    class FakeEngine:
        def __init__(self, plant):
            calls.append(plant)

        def simulate(self, profile):
            return ("results", profile)

    monkeypatch.setattr("gemini.core.engine.engine.Engine", FakeEngine)
    plant = gm.Plant("Run")
    assert plant.simulate("profile") == ("results", "profile")
    assert calls == [plant]
