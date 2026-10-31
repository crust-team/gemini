"""The sample problems of ``inputs/examples/``: only examples and tests read them."""

import json

import gemini as gm
from gemini._utils import paths

HACKATHON_2027 = paths.INPUTS / "examples/hackathon_2027"
SHALLOW_DISTRICT = paths.INPUTS / "examples/shallow_district"
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


def sample_problem(name="problem.json"):
    """Return problem ``name`` of the hackathon sample: the demand, site, constraints, prices."""
    return gm.Problem.from_json(HACKATHON_2027 / name)


def shallow_problem():
    """Return the problem of the ``shallow_district`` sample."""
    return gm.Problem.from_json(SHALLOW_DISTRICT / "problem.json")


def treatment_plant():
    """Return the design with desander and inhibitor dosing, with the site of its problem."""
    plant = gm.plants.from_dict(sample_json("plant_with_treatment.json"))
    return sample_problem("problem_with_treatment.json").apply_site(plant)


def template_dict(name):
    """Return the plant dict of template plant ``name``, without its site."""
    return sample_json("plant.json" if name == SAMPLE_PLANT else f"templates/{name}.json")


def template_plant(name):
    """Return template plant ``name`` with the site of the sample problem applied."""
    return sample_problem().apply_site(gm.plants.from_dict(template_dict(name)))


def filled_plant(name):
    """Return plant ``name`` with values: of the sample problem for a template, else its example."""
    return template_plant(name) if name in (SAMPLE_PLANT, *TEMPLATES) else gm.plants.example(name)
