"""Writing a built plant: stated values stay as written while they are true."""

import gemini as gm
from gemini.modules.plants import writer


def test_a_stated_unit_string_stays_while_the_value_is_unchanged():
    """The unit string is kept; a changed value is written in SI; unstated defaults stay out."""
    plant = gm.Plant("Units")
    plant.add("Pipe", "pipe", length="100 ft")
    assert plant.to_spec()["modules"]["pipe"]["params"] == {"length": "100 ft"}
    plant.set_params("pipe", {"length": 1500.0})
    assert plant.to_spec()["modules"]["pipe"]["params"] == {"length": 1500.0}


def test_a_value_set_since_is_added():
    """A parameter nobody stated is written once it differs from its starting value."""
    plant = gm.Plant("Added")
    plant.add("Pipe", "pipe")
    assert plant.to_spec()["modules"]["pipe"] == {"type": "Pipe", "params": {}}
    plant.set_params("pipe", {"inner_diameter": 0.3})
    assert plant.to_spec()["modules"]["pipe"]["params"] == {"inner_diameter": 0.3}


def test_a_group_writes_its_children_and_a_plant_its_registered_name():
    """Groups nest ``modules``; a nested plant is written by name."""
    plant = gm.Plant("Groups")
    plant.add("ModuleDict", "filters")
    plant.add("Filter", "filters.hot")
    plant.add("Doublet", "doublet")
    modules = plant.to_spec()["modules"]
    assert modules["filters"] == {
        "type": "ModuleDict",
        "modules": {"hot": {"type": "Filter", "params": {}}},
    }
    assert modules["doublet"]["type"] == "Doublet"
    assert writer.type_name(plant.doublet) == "Doublet"


def test_baseline_is_the_starting_values_of_the_tree():
    """A nested plant's baseline holds its dotted parameter names."""
    assert "reservoir.skin" in writer.baseline_of(gm.plants.library.build("Doublet"))
