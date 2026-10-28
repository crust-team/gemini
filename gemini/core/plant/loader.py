"""Build a Plant from project configuration."""

import json
import logging
import os

from gemini.core.data.influxdb_aveva_reader_db import InfluxdbAvevaReaderDB
from gemini.core.data.influxdb_csv_reader_db import InfluxdbCSVReaderDB
from gemini.core.plant.plant import Plant
from gemini.core.plant.units.boosterpump.unit import BoosterPumpUnit
from gemini.core.plant.units.degasser.unit import DegasserUnit
from gemini.core.plant.units.esp.unit import ESPUnit
from gemini.core.plant.units.filter.unit import FilterUnit
from gemini.core.plant.units.gasboiler.unit import GasBoilerUnit
from gemini.core.plant.units.heatexchanger.unit import HeatExchangerUnit
from gemini.core.plant.units.injectionpump.unit import InjectionPumpUnit
from gemini.core.plant.units.injectionwell.unit import InjectionWellUnit
from gemini.core.plant.units.productionwell.unit import ProductionWellUnit
from gemini.core.plant.units.reservoir.unit import ReservoirUnit

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

UNIT_FACTORIES = {
    "esp": ESPUnit,
    "injection_pump": InjectionPumpUnit,
    "production_well": ProductionWellUnit,
    "injection_well": InjectionWellUnit,
    "degasser": DegasserUnit,
    "heat_exchanger": HeatExchangerUnit,
    "filter": FilterUnit,
    "reservoir": ReservoirUnit,
    "booster_pump": BoosterPumpUnit,
    "gas_boiler": GasBoilerUnit,
}


def setup(project_path, plant_name, *, database=None):
    """Set up the plant.

    :param str project_path: location of the project folder.
    :param str plant_name: the plant name or location name.
    """
    logger.info("Boot application %s", plant_name)

    plant = Plant()
    plant.project_path = project_path
    plant.name = plant_name

    project_folder = os.path.join(plant.project_path, plant.name)
    with open(os.path.join(project_folder, "plant.conf"), "r", encoding="utf-8") as jsonfile:
        cfg = json.load(jsonfile)
        plant.update_parameters(cfg)

    with open(os.path.join(project_folder, "diagram.json"), "r", encoding="utf-8") as jsonfile:
        plant.diagram = json.load(jsonfile)

    plant = boot_unit(plant)
    if database is None:
        plant = boot_database(plant)
    else:
        plant.add_database(database, "measured")
        plant.register_tags()
        plant.connect_database()

    return plant


def boot_unit(plant):
    """Boot unit in the plant."""
    logger.info("Boot Unit Plant")

    project_folder = os.path.join(plant.project_path, plant.name)
    for file in os.listdir(project_folder):
        if file.endswith(".param"):
            with open(os.path.join(project_folder, file), "r", encoding="utf-8") as jsonfile:
                unitfile = json.load(jsonfile)
                unit_factory = UNIT_FACTORIES.get(unitfile["type"])
                if unit_factory is None:
                    logger.error("UNIT %s not yet implemented", unitfile["type"])
                    continue

                unit = unit_factory(unitfile["id"], unitfile["name"], plant)

                unit.set_parameters(unitfile["parameters"])
                unit.set_tagnames(unitfile["tagnames"])

                plant.add_unit(unit)

    plant.connect_unit()

    plant.link_unit()

    return plant


def boot_database(plant):
    """Start up the boot database."""
    logger.info("Boot Database")

    # csv database for manual upload
    category = "measured"
    meas_database = InfluxdbCSVReaderDB(category)
    plant.add_database(meas_database, category)

    # add external measured database
    if plant.parameters["database"]["external_database"] == "avevadb":
        category = "measured"
        meas_database = InfluxdbAvevaReaderDB(category)
        plant.add_database(meas_database, category)

    plant.register_tags()
    plant.connect_database()

    return plant
