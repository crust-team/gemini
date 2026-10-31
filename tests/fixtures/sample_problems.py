"""The sample problems of ``inputs/examples/``: only examples and tests read them."""

import json

import gemini as gm
from gemini._utils import paths

HACKATHON_2027 = paths.INPUTS / "examples/hackathon_2027"
SAMPLE_PLANT = "HeatingCoolingPlant"
"""The class of the design in ``plant.json``; the other template plants are in ``templates/``."""
TEMPLATES = (
    "HeatingPlant",
    "HeatingAbsorptionCoolingPlant",
    "HeatingHeatPumpCoolingPlant",
    "HeatingFullCoolingPlant",
)


def sample_json(name):
    """Return the JSON file ``name`` of the sample problem as data."""
    return json.loads((HACKATHON_2027 / name).read_text())


def treatment_plant():
    """Return the design with desander and inhibitor dosing of the sample problem."""
    return gm.plants.from_dict(sample_json("plant_with_treatment.json"))


def template_dict(name):
    """Return the plant dict of template plant ``name`` with the values of the sample problem."""
    return sample_json("plant.json" if name == SAMPLE_PLANT else f"templates/{name}.json")


def template_plant(name):
    """Return template plant ``name`` with the values of the sample problem."""
    return gm.plants.from_dict(template_dict(name))


def filled_plant(name):
    """Return plant ``name`` with values: of the sample problem for a template, else its example."""
    return template_plant(name) if name in (SAMPLE_PLANT, *TEMPLATES) else gm.plants.example(name)
