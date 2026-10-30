"""The generated plant specs: sizes, shipped default files, wiring and the call order."""

import pytest

import gemini as gm
from gemini.modules.plants import generators, library
from gemini.modules.plants.plan import compile_plan

SIZES = [(1, 1), (2, 1), (1, 3), (3, 2)]


def test_shipped_files_are_the_generator_output_of_the_default_size():
    """The spec files of the default sizes are exactly what the generators return."""
    assert library.shipped("MultiWellPlant") == generators.multi_well_spec()
    assert library.shipped("DistrictNetwork") == generators.district_network_spec()


@pytest.mark.parametrize(("producers", "injectors"), SIZES)
def test_a_well_field_spec_is_valid_and_round_trips(producers, injectors):
    """Every size validates without problems and a built plant writes the same spec."""
    spec = generators.multi_well_spec(producers, injectors)
    assert gm.plants.validate(spec) == []
    assert gm.plants.from_spec(spec).to_spec() == spec
    assert len(spec["modules"]["mixers"]["modules"]) == producers - 1
    assert len(spec["modules"]["splitters"]["modules"]) == injectors - 1


@pytest.mark.parametrize(("consumers", "service"), [(1, "heating"), (3, "cooling"), (2, "heating")])
def test_a_network_spec_is_valid_and_round_trips(consumers, service):
    """Every size and service validates and a built plant writes the same spec."""
    spec = generators.district_network_spec(consumers, service)
    assert gm.plants.validate(spec) == []
    assert gm.plants.from_spec(spec).to_spec() == spec
    kinds = {item["type"] for item in spec["modules"]["substations"]["modules"].values()}
    assert kinds == {generators.SUBSTATIONS[service]}
    assert ("heat_supplied" in spec["outputs"]) == (service == "heating")


def _order(spec):
    return [step.path for step in compile_plan(gm.plants.from_spec(spec)).steps]


def test_a_well_field_produces_then_mixes_then_injects():
    """The plan calls every production limb, the mixers, then each splitter before its limb."""
    limb = ["reservoir", "well", "esp", "riser"]
    expected = [f"producers.{index}.{name}" for index in range(3) for name in limb]
    expected += ["mixers.0", "mixers.1", "splitters.0", "injectors.0.well", "injectors.0.sink"]
    expected += ["injectors.1.well", "injectors.1.sink"]
    assert _order(generators.multi_well_spec(3, 2)) == expected


def test_a_network_splits_serves_in_order_and_mixes():
    """The plan calls the splitters before the substations, and the mixers after them."""
    expected = ["pump", "supply_pipe", "splitters.0", "splitters.1"]
    expected += ["substations.0", "substations.1", "substations.2", "mixers.0", "mixers.1"]
    assert _order(generators.district_network_spec(3)) == expected + ["return_pipe"]


def test_sizes_below_one_and_unknown_services_raise():
    """A structural argument that cannot build a plant is a configuration error."""
    with pytest.raises(gm.errors.ConfigurationError, match="producers = 0, injectors = 1"):
        generators.multi_well_spec(0, 1)
    with pytest.raises(gm.errors.ConfigurationError, match="consumers = 0"):
        generators.district_network_spec(0)
    with pytest.raises(gm.errors.ConfigurationError, match="service = 'steam'"):
        generators.district_network_spec(2, "steam")
